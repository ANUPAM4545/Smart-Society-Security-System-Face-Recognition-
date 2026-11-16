"""Local browser interface: python web.py, then http://127.0.0.1:8765."""
import argparse
import base64
import importlib.util
import json
import math
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from security.core import Database, match
from security.evaluation import build_report, markdown_report, save_report

ROOT = Path(__file__).resolve().parent
VISION_LOCK = threading.Lock()


def backend_ready():
    try:
        if not all(importlib.util.find_spec(name) is not None for name in ('cv2', 'face_recognition', 'numpy')):
            return False
        from security import vision
        return callable(vision.faces)
    except (ImportError, OSError, RuntimeError):
        return False


def decode_frame(value):
    if not isinstance(value, str) or not value.startswith('data:image/jpeg;base64,'):
        raise ValueError('A JPEG camera frame is required.')
    import cv2
    import numpy as np
    raw = base64.b64decode(value.split(',', 1)[1], validate=True)
    if len(raw) > 3_000_000:
        raise ValueError('Image too large.')
    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or max(frame.shape[:2]) > 1920:
        raise ValueError('Invalid image or resolution above 1920 pixels.')
    return frame


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, db_path):
        super().__init__(address, Handler)
        self.db_path = db_path
        self.cooldown = {}
        self.cooldown_lock = threading.Lock()

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(60)
        return connection, address


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Do not log images, identity details, or request payloads.
        return

    def respond(self, status, value, content_type='application/json'):
        data = json.dumps(value).encode() if content_type == 'application/json' else value
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def local_request(self):
        port = self.server.server_port
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if self.headers.get('Host') not in hosts:
            return False
        origin = self.headers.get('Origin')
        return origin is None or origin in {f'http://{host}' for host in hosts}

    def do_GET(self):
        if not self.local_request():
            self.respond(403, {'error': 'Local requests only.'})
            return
        static = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                  '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if self.path in static:
            filename, content_type = static[self.path]
            self.respond(200, (ROOT/'web'/filename).read_bytes(), content_type)
            return
        db = Database(self.server.db_path)
        try:
            if self.path == '/api/status':
                residents, events = db.residents(), db.events(limit=100)
                self.respond(200, dict(vision_ready=backend_ready(), residents=residents, events=events[:100],
                                      event_count=db.event_count(),
                                      active_count=sum(bool(r['active'] and r['samples']) for r in residents)))
            else:
                self.respond(404, {'error': 'Not found'})
        finally:
            db.close()

    def do_POST(self):
        if not self.local_request() or self.headers.get('Content-Type') != 'application/json':
            self.respond(403, {'error': 'Same-origin JSON requests only.'})
            return
        db = None
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 15_000_000:
                raise ValueError('Invalid request size.')
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError('JSON object required.')
            db = Database(self.server.db_path)
            if self.path == '/api/resident-status':
                if not isinstance(payload.get('id'), str) or not isinstance(payload.get('active'), bool):
                    raise ValueError('Resident ID and boolean active status required.')
                db.set_active(payload['id'], payload['active'])
                self.respond(200, {'ok': True})
            elif self.path in ('/api/enroll', '/api/recognize', '/api/evaluate'):
                if not backend_ready():
                    self.respond(503, {'error': 'Recognition backend unavailable. Install requirements.txt, then restart the server.'})
                    return
                with VISION_LOCK:
                    from security.vision import faces, validate_samples
                    if self.path == '/api/enroll':
                        if payload.get('consent') is not True:
                            raise ValueError('Enrollment consent is required.')
                        details = [payload.get(k) for k in ('id', 'name', 'apartment')]
                        if not all(isinstance(v, str) and 0 < len(v.strip()) <= 100 for v in details):
                            raise ValueError('Enter resident ID, name, and apartment (maximum 100 characters).')
                        images = payload.get('images')
                        if not isinstance(images, list) or not 3 <= len(images) <= 5:
                            raise ValueError('Capture 3 to 5 samples.')
                        samples = []
                        for image in images:
                            detected = faces(decode_frame(image))
                            if len(detected) != 1:
                                raise ValueError('Each sample must contain exactly one face. Clear samples and retry.')
                            samples.append(detected[0][1].tolist())
                        validate_samples(samples)
                        db.enroll(*details, samples)
                        self.respond(200, {'ok': True, 'samples': len(samples)})
                    elif self.path == '/api/evaluate':
                        if payload.get('held_out') is not True:
                            raise ValueError('Confirm test images were not used for enrollment or tuning.')
                        threshold = float(payload.get('threshold', 0.48))
                        if not math.isfinite(threshold) or not 0 < threshold < 1:
                            raise ValueError('Threshold must be between 0 and 1.')
                        items = payload.get('trials')
                        if not isinstance(items, list) or not 1 <= len(items) <= 30:
                            raise ValueError('Provide 1 to 30 test images per evaluation.')
                        gallery = db.gallery()
                        active_ids = {r[0] for r in gallery}
                        if not active_ids:
                            raise ValueError('Enroll at least one active resident first.')
                        trials = []
                        for index, item in enumerate(items, 1):
                            if not isinstance(item, dict):
                                raise ValueError(f'Invalid trial {index}.')
                            expected = item.get('expected_id') or None
                            if expected is not None and not isinstance(expected, str):
                                raise ValueError(f'Trial {index}: expected_id must be a resident ID or blank.')
                            if expected is not None and expected not in active_ids:
                                raise ValueError(f'Trial {index}: expected_id is not an active resident.')
                            name = item.get('filename', f'trial-{index}.jpg')
                            if not isinstance(name, str) or len(name) > 200:
                                raise ValueError('Invalid test image filename.')
                            detected = faces(decode_frame(item.get('image')))
                            if len(detected) != 1:
                                raise ValueError(f'Trial {index}: exactly one face is required. No report saved.')
                            trials.append(dict(image=name, expected_id=expected,
                                               **match(detected[0][1], gallery, threshold)))
                        report = build_report(trials, threshold, active_ids)
                        save_report(report, ROOT/'reports')
                        self.respond(200, {'report': report, 'markdown': markdown_report(report)})
                    else:
                        threshold = float(payload.get('threshold', 0.48))
                        if not math.isfinite(threshold) or not 0 < threshold < 1:
                            raise ValueError('Threshold must be between 0 and 1.')
                        frame = decode_frame(payload.get('image'))
                        gallery = db.gallery()
                        if not gallery:
                            raise ValueError('Enroll at least one active resident first.')
                        results = []
                        for box, encoding in faces(frame):
                            result = match(encoding, gallery, threshold)
                            result['box'] = box
                            results.append(result)
                            key = result['resident_id'] or 'unknown'
                            with self.server.cooldown_lock:
                                now = time.monotonic()
                                if now - self.server.cooldown.get(key, -100) >= 5:
                                    db.log(result)
                                    self.server.cooldown[key] = now
                        self.respond(200, {'faces': results, 'width': frame.shape[1], 'height': frame.shape[0]})
            else:
                self.respond(404, {'error': 'Not found'})
        except (ValueError, TypeError, KeyError, sqlite3.Error) as exc:
            self.respond(400, {'error': str(exc)})
        except ImportError:
            self.respond(503, {'error': 'Vision dependencies could not load. Check the local Python installation.'})
        except Exception:
            self.respond(500, {'error': 'Frame processing failed. Check the camera image and installed vision dependencies.'})
        finally:
            if db is not None:
                db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Smart Society local browser dashboard')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    try:
        server = LocalServer(('127.0.0.1', args.port), ROOT/'data'/'society.db')
    except OSError as exc:
        parser.exit(1, f'Cannot start local server on port {args.port}: {exc}\n')
    print(f'Smart Society running at http://127.0.0.1:{server.server_port}', flush=True)
    print('Recognition backend: ' + ('ready' if backend_ready() else 'missing dependencies'), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

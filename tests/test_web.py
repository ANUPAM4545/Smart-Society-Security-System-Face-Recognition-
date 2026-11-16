"""HTTP handler tests without opening a network port."""
import io
import json
import tempfile
import threading
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from security.core import Database
from web import Handler


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = SimpleNamespace(server_port=8765, db_path=Path(self.temp.name)/'test.db',
                                      cooldown={}, cooldown_lock=threading.Lock())

    def tearDown(self):
        self.temp.cleanup()

    def request(self, path, payload=None, host='127.0.0.1:8765', origin=None):
        handler = Handler.__new__(Handler)
        handler.server = self.server
        handler.path = path
        handler.request_version = 'HTTP/1.1'
        handler.requestline = 'GET ' + path
        handler.command = 'GET' if payload is None else 'POST'
        handler.headers = {'Host': host}
        if origin:
            handler.headers['Origin'] = origin
        handler.wfile = io.BytesIO()
        if payload is not None:
            raw = json.dumps(payload).encode()
            handler.headers.update({'Content-Type': 'application/json', 'Content-Length': str(len(raw))})
            handler.rfile = io.BytesIO(raw)
            handler.do_POST()
        else:
            handler.do_GET()
        head, body = handler.wfile.getvalue().split(b'\r\n\r\n', 1)
        return int(head.split()[1]), body

    def test_dashboard_and_status(self):
        code, body = self.request('/')
        self.assertEqual(code, 200)
        self.assertIn(b'Start camera', body)
        code, body = self.request('/api/status')
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)['active_count'], 0)
        self.assertEqual(self.request('/app.js')[0], 200)
        self.assertEqual(self.request('/style.css')[0], 200)
        self.assertEqual(self.request('/../security/core.py')[0], 404)

    def test_reject_foreign_host_and_origin(self):
        self.assertEqual(self.request('/api/status', host='evil.example:8765')[0], 403)
        self.assertEqual(self.request('/api/resident-status', {}, origin='https://evil.example')[0], 403)

    def test_missing_backend_is_explicit(self):
        with patch('web.backend_ready', return_value=False):
            code, body = self.request('/api/recognize', {'image': 'test'})
        self.assertEqual(code, 503)
        self.assertIn('unavailable', json.loads(body)['error'])

    def test_resident_activation_and_validation(self):
        db = Database(self.server.db_path)
        db.enroll('R01','Resident','A1',[[0.0]*128])
        db.close()
        self.assertEqual(self.request('/api/resident-status', {'id':'R01','active':False})[0], 200)
        self.assertEqual(json.loads(self.request('/api/status')[1])['active_count'], 0)
        self.assertEqual(self.request('/api/resident-status', {'id':'R01','active':'false'})[0], 400)

    def fake_vision(self):
        class Encoding(list):
            def tolist(self):
                return list(self)
        def faces(frame):
            if frame.marker == 'no-face':
                return []
            result = [((10,100,120,20), Encoding([1.0 if frame.marker == 'unknown' else 0.0]*128))]
            return result*2 if frame.marker == 'two-faces' else result
        module = types.ModuleType('security.vision')
        module.faces = faces
        module.validate_samples = lambda samples: samples
        return module

    def vision_request(self, path, payload):
        with patch('web.backend_ready', return_value=True), \
             patch('web.decode_frame', side_effect=lambda marker: SimpleNamespace(shape=(480,640,3),marker=marker)), \
             patch.dict('sys.modules', {'security.vision': self.fake_vision()}), \
             patch('web.ROOT', Path(self.temp.name)):
            return self.request(path,payload)

    def enroll(self):
        return self.vision_request('/api/enroll', {'id':'R01','name':'Resident','apartment':'A1',
                                                  'consent':True,'images':['known']*3})

    def test_full_enroll_recognize_log_deactivate_flow(self):
        self.assertEqual(self.enroll()[0],200)
        for _ in range(2):
            code, body = self.vision_request('/api/recognize', {'image':'known','threshold':0.48})
            self.assertEqual(code,200)
            self.assertEqual(json.loads(body)['faces'][0]['decision'],'ALLOWED')
        data = json.loads(self.request('/api/status')[1])
        self.assertEqual(data['event_count'],1)  # duplicate frames are throttled
        code, body = self.vision_request('/api/recognize', {'image':'unknown'})
        self.assertEqual(json.loads(body)['faces'][0]['decision'],'REJECTED')
        self.request('/api/resident-status', {'id':'R01','active':False})
        self.assertEqual(self.vision_request('/api/recognize', {'image':'known'})[0],400)

    def test_failed_enrollment_does_not_save_partial_samples(self):
        for images in (['known','known','no-face'], ['known','known','two-faces']):
            code,_ = self.vision_request('/api/enroll', {'id':'R01','name':'Resident','apartment':'A1',
                                                        'consent':True,'images':images})
            self.assertEqual(code,400)
            self.assertEqual(json.loads(self.request('/api/status')[1])['residents'],[])

    def test_browser_evaluation_saves_real_computed_report(self):
        self.enroll()
        code, body = self.vision_request('/api/evaluate', {'held_out':True, 'threshold':0.48,'trials':[
            {'filename':'known.jpg','expected_id':'R01','image':'known'},
            {'filename':'unknown.jpg','expected_id':None,'image':'unknown'}]})
        self.assertEqual(code,200)
        report = json.loads(body)['report']
        self.assertEqual(report['metrics']['identity_accuracy'],1)
        self.assertEqual(report['metrics']['trials'],2)
        self.assertTrue((Path(self.temp.name)/'reports'/'evaluation.md').exists())
        self.assertEqual(json.loads(self.request('/api/status')[1])['event_count'],0)

    def test_evaluation_rejects_bad_image_without_report(self):
        self.enroll()
        code,_ = self.vision_request('/api/evaluate', {'held_out':True,'trials':[
            {'filename':'bad.jpg','expected_id':'R01','image':'no-face'}]})
        self.assertEqual(code,400)
        self.assertFalse((Path(self.temp.name)/'reports').exists())

    def test_consent_and_threshold_required(self):
        code,_ = self.vision_request('/api/enroll', {'id':'R01','name':'Resident','apartment':'A1',
                                                    'consent':False,'images':['known']*3})
        self.assertEqual(code,400)
        self.enroll()
        self.assertEqual(self.vision_request('/api/recognize', {'image':'known','threshold':float('nan')})[0],400)
        self.assertEqual(self.vision_request('/api/evaluate', {'held_out':False,'trials':[]})[0],400)


if __name__ == '__main__':
    unittest.main()

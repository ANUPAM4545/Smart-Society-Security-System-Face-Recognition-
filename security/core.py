"""Database and matching logic; usable without camera or third-party packages."""
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def vector(values):
    values = [float(x) for x in values]
    if len(values) != 128 or not all(math.isfinite(x) for x in values):
        raise ValueError('A face encoding must contain 128 finite numbers.')
    return values


class Database:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys = ON')
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS residents (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, apartment TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS encodings (
          id INTEGER PRIMARY KEY, resident_id TEXT NOT NULL REFERENCES residents(id),
          vector TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
          resident_id TEXT REFERENCES residents(id), decision TEXT NOT NULL,
          distance REAL, reason TEXT NOT NULL);
        ''')

    def close(self):
        self.conn.close()

    def enroll(self, resident_id, name, apartment, encodings):
        resident_id, name, apartment = [x.strip() for x in (resident_id, name, apartment)]
        if not all((resident_id, name, apartment)):
            raise ValueError('Resident ID, name and apartment are required.')
        encodings = [vector(x) for x in encodings]
        if not encodings:
            raise ValueError('At least one valid face sample is required.')
        with self.conn:
            existing = self.conn.execute('SELECT * FROM residents WHERE id=?', (resident_id,)).fetchone()
            if existing and (existing['name'] != name or existing['apartment'] != apartment):
                raise ValueError('This ID belongs to another resident. Use its original name/apartment.')
            if not existing:
                self.conn.execute('INSERT INTO residents VALUES (?, ?, ?, 1, ?)',
                                  (resident_id, name, apartment, datetime.now(timezone.utc).isoformat()))
            self.conn.executemany('INSERT INTO encodings(resident_id,vector) VALUES (?,?)',
                                  [(resident_id, json.dumps(x)) for x in encodings])

    def residents(self):
        return [dict(x) for x in self.conn.execute('''
          SELECT r.*, COUNT(e.id) AS samples FROM residents r
          LEFT JOIN encodings e ON r.id=e.resident_id GROUP BY r.id ORDER BY r.id''')]

    def set_active(self, resident_id, active):
        with self.conn:
            result = self.conn.execute('UPDATE residents SET active=? WHERE id=?', (int(active), resident_id))
            if result.rowcount == 0:
                raise ValueError('Resident ID not found.')

    def gallery(self):
        return [(r['resident_id'], r['name'], json.loads(r['vector'])) for r in self.conn.execute('''
          SELECT e.*, r.name FROM encodings e JOIN residents r ON r.id=e.resident_id WHERE r.active=1''')]

    def log(self, result):
        with self.conn:
            self.conn.execute('INSERT INTO events(timestamp,resident_id,decision,distance,reason) VALUES (?,?,?,?,?)',
                              (datetime.now(timezone.utc).isoformat(), result['resident_id'],
                               result['decision'], result['distance'], result['reason']))

    def events(self, limit=None):
        if limit is None:
            return [dict(r) for r in self.conn.execute('SELECT * FROM events ORDER BY id DESC')]
        return [dict(r) for r in self.conn.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (int(limit),))]

    def event_count(self):
        return self.conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]


def match(encoding, gallery, threshold=0.48, margin=0.04):
    if not 0 < threshold < 1 or not 0 <= margin < 1:
        raise ValueError('Invalid matching threshold or ambiguity margin.')
    encoding = vector(encoding)
    best = {}
    for resident_id, name, sample in gallery:
        distance = math.sqrt(sum((a-b)**2 for a,b in zip(encoding, vector(sample))))
        if resident_id not in best or distance < best[resident_id][0]:
            best[resident_id] = (distance, name)
    ranked = sorted(best.items(), key=lambda x: x[1][0])
    result = dict(resident_id=None, name='Unknown', decision='REJECTED', distance=None, reason='No active residents')
    if not ranked:
        return result
    resident_id, (distance, name) = ranked[0]
    result['distance'] = distance
    result['reason'] = 'Distance above threshold'
    if distance <= threshold:
        if len(ranked) > 1 and ranked[1][1][0] - distance < margin:
            result['reason'] = 'Ambiguous identity; manual review required'
        else:
            result.update(resident_id=resident_id, name=name, decision='ALLOWED', reason='Resident recognized')
    return result


def metrics(rows):
    """Binary entry metrics plus exact identity accuracy, including wrong-resident accepts."""
    tp = tn = fp = fn = identity_correct = misidentified = 0
    for expected, predicted in rows:
        known, allowed = expected is not None, predicted is not None
        tp += known and allowed
        tn += not known and not allowed
        fp += not known and allowed
        fn += known and not allowed
        identity_correct += expected == predicted
        misidentified += known and allowed and expected != predicted
    total = len(rows)
    ratio = lambda a,b: a/b if b else None
    return dict(trials=total, true_positive=tp, true_negative=tn, false_positive=fp,
                false_negative=fn, misidentified=misidentified,
                entry_accuracy=ratio(tp+tn,total), identity_accuracy=ratio(identity_correct,total),
                false_positive_rate=ratio(fp,fp+tn), false_negative_rate=ratio(fn,fn+tp))

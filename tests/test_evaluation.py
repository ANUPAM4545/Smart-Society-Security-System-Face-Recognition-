"""Exercise actual CSV/report flow using deterministic encodings, without a camera."""
import contextlib
import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from main import evaluate
from security.core import Database


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root/'test.db')
        self.db.enroll('R01','Test Resident','A1',[[0.0]*128])
        self.manifest = self.root/'trials.csv'
        self.output = self.root/'reports'
        fake = types.ModuleType('security.vision')
        fake.image_encoding = lambda p: [0.0]*128 if p.name == 'known.jpg' else [1.0]*128
        self.patcher = patch.dict('sys.modules', {'security.vision': fake})
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.db.close()
        self.temp.cleanup()

    def run_report(self):
        with contextlib.redirect_stdout(io.StringIO()):
            evaluate(self.db,self.manifest,0.48,self.output)

    def test_known_and_unknown_report(self):
        self.manifest.write_text('image,expected_id\nknown.jpg,R01\nunknown.jpg,\n')
        self.run_report()
        report = json.loads((self.output/'evaluation.json').read_text())
        self.assertEqual(report['metrics']['trials'],2)
        self.assertEqual(report['metrics']['identity_accuracy'],1)
        self.assertEqual(report['metrics']['false_positive_rate'],0)
        self.assertTrue((self.output/'evaluation.md').exists())

    def test_reject_bad_rows_before_writing_report(self):
        for data in ['image,expected_id\nknown.jpg\n', 'image,expected_id\n,R01\n',
                     'image,expected_id\nknown.jpg,R01,extra\n', 'image,expected_id\n']:
            with self.subTest(data=data):
                self.manifest.write_text(data)
                with self.assertRaises(ValueError):
                    self.run_report()
                self.assertFalse(self.output.exists())

    def test_reject_unknown_expected_identity(self):
        self.manifest.write_text('image,expected_id\nknown.jpg,R99\n')
        with self.assertRaisesRegex(ValueError,'expected_id'):
            self.run_report()


if __name__ == '__main__':
    unittest.main()

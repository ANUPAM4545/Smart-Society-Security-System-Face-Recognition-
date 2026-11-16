import tempfile
import unittest
from pathlib import Path
from security.core import Database, match, metrics


def enc(first=0):
    return [first]+[0.0]*127


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'test.db'
        self.db = Database(self.path)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_persistence_and_deactivation(self):
        self.db.enroll('R01','Alice','A1',[enc()])
        self.db.close()
        self.db = Database(self.path)
        self.assertEqual(match(enc(),self.db.gallery())['resident_id'],'R01')
        self.db.set_active('R01',False)
        self.assertEqual(match(enc(),self.db.gallery())['decision'],'REJECTED')

    def test_twenty_distinct_residents(self):
        for n in range(20):
            self.db.enroll(str(n),f'Resident {n}',str(n),[enc(n)])
        self.assertEqual(len(self.db.residents()),20)
        self.assertEqual(match(enc(18),self.db.gallery())['resident_id'],'18')

    def test_unknown_and_empty(self):
        self.assertEqual(match(enc(),[])['decision'],'REJECTED')
        self.assertEqual(match(enc(2),[('A','Alice',enc())])['decision'],'REJECTED')

    def test_ambiguity_across_people_only(self):
        gallery = [('A','Alice',enc()),('A','Alice',enc(0.01))]
        self.assertEqual(match(enc(),gallery)['decision'],'ALLOWED')
        gallery.append(('B','Bob',enc(0.02)))
        self.assertEqual(match(enc(),gallery)['decision'],'REJECTED')

    def test_threshold_boundary(self):
        gallery = [('A','Alice',enc())]
        self.assertEqual(match(enc(0.48),gallery)['decision'],'ALLOWED')
        self.assertEqual(match(enc(0.481),gallery)['decision'],'REJECTED')

    def test_invalid_vectors_and_conflicting_id(self):
        with self.assertRaises(ValueError):
            self.db.enroll('A','Alice','1',[[float('nan')]*128])
        self.assertEqual(self.db.residents(),[])
        self.db.enroll('A','Alice','1',[enc()])
        with self.assertRaises(ValueError):
            self.db.enroll('A','Bob','2',[enc()])
        self.assertEqual(self.db.residents()[0]['samples'],1)

    def test_log(self):
        self.db.enroll('A','Alice','1',[enc()])
        self.db.log(match(enc(),self.db.gallery()))
        self.db.log(match(enc(3),self.db.gallery()))
        self.assertEqual([r['decision'] for r in self.db.events()],['REJECTED','ALLOWED'])

    def test_metrics_and_identity_errors(self):
        report = metrics([('A','A'),('A',None),(None,'A'),(None,None),('B','A')])
        self.assertEqual(report['false_positive'],1)
        self.assertEqual(report['false_negative'],1)
        self.assertEqual(report['misidentified'],1)
        self.assertEqual(report['identity_accuracy'],0.4)
        self.assertEqual(report['entry_accuracy'],0.6)
        self.assertIsNone(metrics([])['entry_accuracy'])


if __name__ == '__main__':
    unittest.main()

import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_store import connect, initialize, import_content


class IntradayStorageTest(unittest.TestCase):
    def test_roundtrip_idempotence_and_invalid_snapshot_preserves_data(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'test.sqlite3'
            initialize(target)
            path = 'core_index/0AMV-intraday/2026-09-24.csv'
            content = (b'date,time,amv,volume_candidate,amount_candidate,source_file\n'
                       b'2026-09-24,09:30:59,100352.6015625,3437092096,34035009536,a.fde\n'
                       b'2026-09-24,09:31:59,100544.8046875,4940845056,50197639168,a.fde\n')
            with connect(target) as db:
                self.assertTrue(import_content(db, path, content))
                self.assertFalse(import_content(db, path, content))
                self.assertEqual(db.execute('SELECT COUNT(*) FROM indicator_intraday').fetchone()[0], 2)
                with self.assertRaises(ValueError):
                    import_content(db, path, content.replace(b'09:31:59', b'09:30:59'))
                self.assertEqual(db.execute('SELECT content FROM source_files WHERE path=?', (path,)).fetchone()[0], content)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM indicator_daily').fetchone()[0], 0)
                self.assertTrue(import_content(db, path, content.replace(b'100544.8046875', b'100545')))
                self.assertEqual(db.execute('SELECT COUNT(*) FROM indicator_intraday').fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()

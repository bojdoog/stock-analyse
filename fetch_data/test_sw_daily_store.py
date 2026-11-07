import sys
from pathlib import Path
import tempfile
import unittest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'flask_backend'))
import market_store as store
from sw_daily_export import export_daily


class SWStoreTest(unittest.TestCase):
    def test_daily_export_keeps_other_industries_after_partial_update(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dbpath = root / 'test.sqlite'
            for code, close in [('801010.SI',10),('801040.SI',20),('801010.SI',11)]:
                store.save_dataframe(pd.DataFrame([{'ts_code':code,'date':'2026-09-30',
                    'trade_date':'20260930','close':close,'float_mv':400}]),
                    root/'internal'/f'{code}.csv', dbpath, category='sw_index')
            result = export_daily(root/'daily', dbpath)
            self.assertEqual(result, {'files':1,'rows':2})
            rows = pd.read_csv(root/'daily/20260930.csv')
            self.assertEqual(rows.ts_code.tolist(), ['801010.SI','801040.SI'])
            self.assertEqual(rows.close.tolist(), [11,20])

    def test_sw_identity_incremental_upsert_and_raw_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dbpath = root / 'test.sqlite'
            output = root / 'sw_index/801010.SI.csv'
            for day, close in [('2026-09-29', 10), ('2026-09-30', 12), ('2026-09-30', 13)]:
                store.save_dataframe(pd.DataFrame([{'date':day,'close':close,'volume':20000,
                    'amount':30000,'float_mv':400}]), output, dbpath)
            with store.connect(dbpath) as db:
                rows = db.execute("SELECT category,exchange,code,date,close FROM daily_bars ORDER BY date").fetchall()
                self.assertEqual(len(rows), 2)
                self.assertEqual(tuple(rows[-1]), ('sw_index','SI','801010','2026-09-30',13))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM daily_bars WHERE category='index'").fetchone()[0],0)
            csv = pd.read_csv(output)
            self.assertEqual(csv.close.tolist(), [10,13])
            self.assertEqual(csv.float_mv.tolist(), [400,400])


if __name__ == '__main__':
    unittest.main()

import copy
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.sector_activity import calculate


class SectorActivityTests(unittest.TestCase):
    def rows(self):
        return [{'ts_code': code, 'trade_date': f'202409{day:02d}', 'close': 100 + day * factor,
                 'float_mv': 1e10, 'turnover_rate': 2 + day / 10}
                for code, factor in [('a', 1), ('b', 2)] for day in range(10, 22)]

    def calc(self, rows):
        return calculate(rows, ['a', 'b'], {'a': 'A', 'b': 'B'})

    def test_daily_decomposition_and_market_reconciliation(self):
        data = self.calc(self.rows())
        for i in range(1, 12):
            for item in data.values():
                p = item['series'][i]
                self.assertAlmostEqual(p['change'], p['price_contribution'] + p['activity_contribution'])
            total = sum(item['series'][i]['value'] for item in data.values())
            previous = sum(item['series'][i-1]['value'] for item in data.values())
            self.assertAlmostEqual(sum(item['series'][i]['market_contribution'] for item in data.values()), (total/previous-1)*100)

    def test_future_append_does_not_change_history(self):
        rows = self.rows()
        short = self.calc([row for row in rows if row['trade_date'] <= '20240918'])
        full = self.calc(rows)
        for code in short:
            self.assertEqual(short[code]['series'], full[code]['series'][:9])

    def test_index_rebasing_does_not_change_activity(self):
        rows = self.rows()
        changed = copy.deepcopy(rows)
        for row in changed:
            if row['ts_code'] == 'a':
                row['close'] *= 7
        original, rebased = self.calc(rows), self.calc(changed)
        for a, b in zip(original['a']['series'], rebased['a']['series']):
            self.assertAlmostEqual(a['amv'], b['amv'])
            self.assertAlmostEqual(a['value'], b['value'])

    def test_reject_missing_or_duplicate_history(self):
        rows = self.rows()
        with self.assertRaises(ValueError):
            self.calc(rows[1:])
        with self.assertRaises(ValueError):
            self.calc(rows + [rows[0]])
        with self.assertRaises(ValueError):
            self.calc([r for r in rows if not (r['ts_code'] == 'a' and r['trade_date'] == '20240915')])

    def test_amount_and_volume_ratio_exclude_current_day(self):
        rows = [{**self.rows()[0], 'trade_date': (date(2024, 9, 10) + timedelta(days=i)).strftime('%Y%m%d'),
                 'vol': 100 if i < 20 else 300, 'avg_price': 5} for i in range(22)]
        series = calculate(rows, ['a'], {})['a']['series']
        self.assertIsNone(series[19]['volume_ratio'])
        self.assertEqual(series[20]['volume_ratio'], 3)
        self.assertAlmostEqual(series[21]['volume_ratio'], 300 / 110)
        self.assertEqual(series[20]['amount'], 150000)
        self.assertEqual(series[:21], calculate(rows[:21], ['a'], {})['a']['series'])
        rows[0]['vol'] = ''
        self.assertIsNone(calculate(rows, ['a'], {})['a']['series'][20]['volume_ratio'])
        for row in rows:
            row['vol'] = 0
        self.assertIsNone(calculate(rows, ['a'], {})['a']['series'][20]['volume_ratio'])

    def test_kdj_real_prices_warmup_and_future_independence(self):
        rows = [{**row, 'close': 18, 'high': 20, 'low': 10, 'vol': 100} for row in self.rows() if row['ts_code'] == 'a']
        series = calculate(rows, ['a'], {})['a']['series']
        self.assertIsNone(series[7]['k'])
        self.assertAlmostEqual(series[8]['k'], 60)
        self.assertAlmostEqual(series[8]['d'], 160 / 3)
        self.assertAlmostEqual(series[8]['j'], 220 / 3)
        self.assertEqual(series[8]['volume'], 100)
        self.assertEqual(series[:10], calculate(rows[:10], ['a'], {})['a']['series'])
        rows[9]['high'] = ''
        self.assertIsNone(calculate(rows, ['a'], {})['a']['series'][9]['k'])
        for row in rows:
            row.update(close=10, high=10, low=10)
        self.assertAlmostEqual(calculate(rows, ['a'], {})['a']['series'][8]['j'], 50)


if __name__ == '__main__':
    unittest.main()

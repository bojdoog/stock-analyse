import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.sector_volume import build_features


class SectorVolumeTest(unittest.TestCase):
    def setUp(self):
        self.days = [f'2026-01-{day:02d}' for day in range(1, 23)]
        self.catalog = [dict(code='1', name='ETF'), dict(code='2', name='unmapped')]
        self.industries = [dict(ts_code='A', name='a'), dict(ts_code='B', name='b')]
        self.mappings = [dict(etf_code='1', sector_name=name) for name in ['a', 'b', 'a']]
        self.histories = {
            'A': {d: dict(vol=100, amount=50) for d in self.days},
            'B': {d: dict(vol=200, amount=150) for d in self.days},
        }
        self.histories['A'][self.days[20]]['vol'] = 200

    def build(self):
        return build_features(self.days, self.catalog, self.mappings, self.industries, self.histories)

    def test_sum_before_ratio_no_current_day_in_average(self):
        data = self.build()
        f = data['byDate'][self.days[20]]['ETF']
        self.assertAlmostEqual(f['volumeRatio'], 400 / 300)
        self.assertEqual(f['amountShare'], 1)
        self.assertEqual(data['coverageStart'], self.days[20])
        self.assertEqual(data['unmappedNames'], ['unmapped'])
        # Future data must not change the signal-day value.
        self.histories['A'][self.days[21]]['vol'] = 999999
        self.assertEqual(f, self.build()['byDate'][self.days[20]]['ETF'])

    def test_missing_history_is_not_filled(self):
        del self.histories['A'][self.days[5]]
        self.assertEqual(self.build()['byDate'], {})

    def test_missing_amount_is_not_replaced_by_flow_or_volume(self):
        for row in self.histories['A'].values():
            row.pop('amount')
            row['net_buy_amount'] = 100
        data = self.build()
        self.assertFalse(data['amountAvailable'])
        self.assertIsNone(data['byDate'][self.days[20]]['ETF']['amountShare'])

    def test_market_denominator_requires_all_industries(self):
        self.mappings = [dict(etf_code='1', sector_name='a')]
        self.histories['B'][self.days[20]].pop('amount')
        self.assertIsNone(self.build()['byDate'][self.days[20]]['ETF']['amountShare'])


if __name__ == '__main__':
    unittest.main()

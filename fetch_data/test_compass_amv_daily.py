import struct
import unittest

from fetch_data.fetch_compass_amv_daily import FIELDS, MARKER, merge_daily, parse_daily


class CompassDailyTests(unittest.TestCase):
    def fixture(self):
        data = bytearray(80)
        struct.pack_into('<H', data, 20, 28)
        struct.pack_into('<I', data, 30, 250)
        data += MARKER + struct.pack('<I', 20260924)
        data += struct.pack('<IBI', 1, 2, 20260924) + bytes(9)
        data += bytes(16) + MARKER
        data += struct.pack('<I6f', 20260923, 10, 12, 9, 11, 100, 1000)
        data += struct.pack('<I6f', 20260924, 11, 13, 10, 12, 200, 2000)
        data += bytes(248 * 28)
        return data

    def test_index_is_not_mistaken_for_daily_bar(self):
        rows = parse_daily(self.fixture())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1], dict(zip(FIELDS, ['2026-09-24', 11, 13, 10, 12, 200, 2000])))

    def test_truncated_and_wrong_index_rejected(self):
        data = self.fixture()
        with self.assertRaises(ValueError):
            parse_daily(data[:180])
        struct.pack_into('<I', data, 80 + 36 + 5, 20260925)
        with self.assertRaises(ValueError):
            parse_daily(data)

    def test_preserves_existing_and_is_idempotent(self):
        incoming = parse_daily(self.fixture())
        existing = [{**incoming[0], 'volume': '101'}]
        merged, report = merge_daily(existing, incoming)
        self.assertEqual(merged[0]['volume'], '101')
        self.assertEqual(report['added'], 1)
        self.assertEqual(len(report['differences_preserved']), 1)
        self.assertEqual(merge_daily(merged, incoming)[1]['added'], 0)

    def test_ohlc_mismatch_stops_merge(self):
        incoming = parse_daily(self.fixture())
        with self.assertRaises(ValueError):
            merge_daily([{**incoming[0], 'close': 99}], incoming)


if __name__ == '__main__':
    unittest.main()

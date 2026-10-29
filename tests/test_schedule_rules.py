import sys
import unittest
import datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from schedule_rules import calculate, compare, rounded, mincha_from_rounded_end


class RulesTests(unittest.TestCase):
    def calc(self, **inputs):
        return calculate('2026-10-16', inputs, 'SYNTHETIC raw timestamps; no astronomical provider')['expectations']

    def test_rounding_boundaries(self):
        exact = dt.datetime.fromisoformat('2026-10-17T18:55:00-07:00')
        for mode in ['floor', 'ceil']:
            self.assertEqual(rounded(exact, 5, mode), exact)
        self.assertEqual(rounded(exact + dt.timedelta(seconds=1), 5, 'ceil').strftime('%H:%M'), '19:00')
        self.assertEqual(rounded(exact + dt.timedelta(seconds=59)).strftime('%H:%M'), '18:55')
        self.assertEqual(rounded(exact - dt.timedelta(microseconds=1), 5).strftime('%H:%M'), '18:50')

    def test_friday_seconds_and_cap(self):
        e = self.calc(friday_sunset='2026-10-16T18:52:31-07:00')
        self.assertIn('18:52:00', e['friday_shkiyah']['calculated'])
        self.assertIn('18:34:31', e['candles_raw']['calculated'])
        self.assertIn('18:30:00', e['friday_mincha_arvit']['calculated'])
        self.assertIn('18:15:00', e['shir_hashirim']['calculated'])
        self.assertIsNone(e['candles_display']['calculated'])
        e = self.calc(friday_sunset='2026-10-16T18:43:00-07:00')
        self.assertIn('18:25:00', e['friday_mincha_arvit']['calculated'])

    def test_saturday_dependencies(self):
        e = self.calc(tzeit_8_5='2026-10-17T18:54:31-07:00')
        for key, expected in [('saturday_mincha', '17:25'), ('hilchot_second', '15:55'), ('boys_program', '16:25'), ('shiur', '16:25'), ('shabbat_ends', '18:55')]:
            self.assertIn(expected, e[key]['calculated'])
        for key in ['saturday_arvit', 'rabbeinu_tam', 'seudah_shlishi', 'friday_morning']:
            self.assertIsNone(e[key]['calculated'])

    def test_arvit_only_when_definition_confirmed(self):
        e = calculate('2026-10-16', {'tzeit_8_5': '2026-10-17T18:54:31-07:00'}, 'synthetic', True)['expectations']
        self.assertIn('18:50', e['saturday_arvit']['calculated'])

    def test_noach_interval_discrepancy(self):
        bounds = mincha_from_rounded_end('2026-10-17T18:55:00-07:00')
        self.assertEqual(bounds['possible_mincha'], ['2026-10-17T17:25:00-07:00'])
        self.assertIn('18:54:00', bounds['raw_tzeit_lower_exclusive'])

    def test_bireshit_interval_consistency(self):
        bounds = mincha_from_rounded_end('2026-10-10T19:03:00-07:00')
        self.assertEqual(bounds['possible_mincha'], ['2026-10-10T17:35:00-07:00'])

    def test_separate_comparison_values(self):
        e = self.calc(tzeit_8_5='2026-10-17T18:54:31-07:00')
        result = compare('17:30', e['saturday_mincha'], {'value': None, 'provenance': 'pending'})
        self.assertEqual(result['status'], 'mismatch')
        self.assertEqual(result['printed'], '17:30')
        self.assertEqual(compare('19:55', e['saturday_arvit'])['status'], 'unresolved')

    def test_severity_threshold(self):
        e = self.calc(tzeit_8_5='2026-10-17T18:55:00-07:00')['saturday_mincha']
        for printed, severity, gap in [('17:25','match',0), ('17:29','discrepancy',4), ('17:30','discrepancy',5), ('17:31','potential_error',6), ('17:19','potential_error',6)]:
            with self.subTest(printed=printed):
                out = compare(printed, e)
                self.assertEqual(out['severity'], severity)
                self.assertEqual(out['absolute_gap_minutes'], gap)
                self.assertEqual(out['printed'], printed)

    def test_missing_inputs_remain_unresolved(self):
        e = self.calc()
        self.assertIsNone(e['saturday_mincha']['calculated'])
        self.assertIn('08:00', e['early_minyan']['calculated'])
        self.assertIn('08:15', e['sunday_shacharit']['calculated'])
        self.assertIn('08:25', e['monday_shacharit_later']['calculated'])

    def test_date_timezone_and_dst(self):
        for stamp in ['2026-10-16T18:00:00', '2026-10-18T18:00:00-07:00']:
            with self.assertRaises(ValueError):
                self.calc(tzeit_8_5=stamp)
        # UTC input converts to LA on the requested civil date.
        e = self.calc(tzeit_8_5='2026-10-18T01:55:00+00:00')
        self.assertEqual(e['shabbat_ends']['calculated'], '2026-10-17T18:55:00-07:00')
        e = calculate('2026-10-30', {}, 'synthetic')['expectations']
        self.assertTrue(e['hodu']['calculated'].endswith('-07:00'))
        self.assertTrue(e['sunday_shacharit']['calculated'].endswith('-08:00'))
        with self.assertRaises(ValueError):
            calculate('2026-10-17', {}, 'synthetic')
        with self.assertRaises(ValueError):
            calculate('2026-10-16', {}, '')


if __name__ == '__main__':
    unittest.main()

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from flyer_parser import parse, record_source_error


def fixture():
    # SYNTHETIC TEXT, not transcription or OCR of any uploaded image.
    content = [
        ('header', 'Kehilat Bnei Torah'), ('header', 'PARSHAT NOACH'),
        ('header', 'OCTOBER16,2026'), ('header', '9017 W. Pico Blvd LA'),
        ('left', 'Erev Shabbat'), ('left', 'Candle lighting 6:00 PM'),
        ('middle', 'Shabbat morning'), ('middle', 'Shacharit 8:30 AM'),
        ('middle', 'Shema deadline 9:30 AM'),
        ('right', 'Shabbat afternoon'), ('right', 'Arvit 7:55 PM'),
        ('right', 'Seudah Shlishi'), ('left', 'Sunday'),
        ('left', 'Shacharit 8:00 AM'), ('left', 'Monday-Friday'),
        ('left', 'Shacharit 6:30 AM'), ('right', 'Shiurim'),
        ('right', 'Torah class 5:00 PM'),
    ]
    return {'document_id': 'synthetic-noach-rules', 'input_kind': 'synthetic',
            'lines': [{'id': str(i), 'region': r, 'text': t, 'bbox': None} for i, (r, t) in enumerate(content)]}


class ParserTests(unittest.TestCase):
    def test_weekly_anchor_and_dates(self):
        out = parse(fixture())
        self.assertEqual(out['classification'], 'weekly_candidate')
        self.assertEqual(out['shabbat_date'], '2026-10-17')
        self.assertEqual(out['timezone']['value'], 'America/Los_Angeles')
        self.assertFalse(out['automation_eligible'])

    def test_bireshit_friday_anchor(self):
        doc = fixture()
        doc['lines'][1]['text'] = 'PARSHAT BIRESHIT'
        doc['lines'][2]['text'] = 'OCTOBER9,2026'
        self.assertEqual(parse(doc)['shabbat_date'], '2026-10-10')

    def test_unknown_address_does_not_invent_timezone(self):
        doc = fixture()
        doc['lines'][3]['text'] = 'Address illegible'
        self.assertIsNone(parse(doc)['timezone']['value'])

    def test_schema_is_json_and_output_has_required_keys(self):
        # Structural smoke check only; no JSON Schema validator is installed.
        import json
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schema' / 'extraction.schema.json').read_text())
        out = parse(fixture())
        self.assertEqual(set(schema['required']), set(out))
        for entry in out['entries']:
            self.assertEqual(set(schema['$defs']['entry']['required']), set(entry))

    def test_printed_error_is_not_ocr_correction(self):
        out = parse(fixture())
        out = record_source_error(out, '10', 'User confirmed Noach Arvit is a printing mistake; correct value pending')
        e = next(x for x in out['entries'] if x['id'] == '10')
        self.assertEqual(e['normalized_time'], '19:55')
        self.assertEqual(e['printed_time'], '7:55 PM')
        self.assertIsNone(e['correction']['normalized_time'])
        self.assertIn('user_confirmed_source_error', e['issues'])

    def test_correction_is_separate(self):
        # Arbitrary synthetic correction, NOT a claim about the real Noach flyer.
        original = parse(fixture())
        changed = record_source_error(original, '10', 'Synthetic reviewer', '20:00')
        self.assertEqual(changed['entries'][3]['normalized_time'], '19:55')
        self.assertIsNone(original['entries'][3]['correction'])

    def test_categories_and_untimed(self):
        entries = {e['id']: e for e in parse(fixture())['entries']}
        self.assertEqual(entries['5']['category'], 'zman_deadline')
        self.assertEqual(entries['7']['category'], 'service')
        self.assertEqual(entries['17']['category'], 'class_event')
        self.assertIsNone(entries['11']['normalized_time'])
        self.assertIn('untimed_entry', entries['11']['issues'])

    def test_weekdays_not_silently_dated(self):
        e = next(x for x in parse(fixture())['entries'] if x['id'] == '15')
        self.assertIsNone(e['date'])
        self.assertIn('calendar_applicability_unresolved', e['issues'])

    def test_special_overrides_weekly_anchors(self):
        for name in ['Yom Kippur', 'Sukkot', 'Simchat Torah', 'Fast day']:
            doc = fixture()
            doc['lines'][1]['text'] += ' ' + name + ' Shabbat'
            out = parse(doc)
            self.assertEqual(out['classification'], 'unsupported_special')
            self.assertEqual(out['entries'], [])

    def test_missing_anchor(self):
        doc = fixture()
        doc['lines'][0]['text'] = 'Blue and gold Shabbat flyer'
        self.assertEqual(parse(doc)['classification'], 'unknown')

    def test_ambiguous_and_invalid_times(self):
        for text, expected in [('Arvit 7:55', 'meridiem_unresolved'),
                               ('Arvit 7:99 PM', 'invalid_or_unsupported_time'),
                               ('Arvit 7:55 PM / 8:00 PM', 'multiple_times_unresolved')]:
            doc = fixture()
            doc['lines'][10]['text'] = text
            e = next(x for x in parse(doc)['entries'] if x['id'] == '10')
            self.assertIsNone(e['normalized_time'])
            self.assertIn(expected, e['issues'])

    def test_contradictory_duplicate(self):
        doc = fixture()
        doc['lines'].insert(11, {'id': 'extra', 'region': 'right', 'text': 'Arvit 8:00 PM', 'bbox': None})
        es = [x for x in parse(doc)['entries'] if x['label'] == 'Arvit']
        self.assertTrue(all('contradictory_duplicate_time' in x['issues'] for x in es))

    def test_region_isolation_and_evidence_preservation(self):
        doc = fixture()
        doc['lines'][10]['region'] = 'unknown_column'
        doc['lines'][7]['bbox'] = [100, 200, 50, 20]
        original = copy.deepcopy(doc)
        out = parse(doc)
        self.assertIn('10', out['unparsed_line_ids'])
        self.assertEqual(out['evidence_lines'], original['lines'])
        self.assertEqual(doc, original)

    def test_bad_date_and_conflicting_date(self):
        doc = fixture()
        doc['lines'][2]['text'] = 'OCTOBER17,2026'
        self.assertIsNone(parse(doc)['shabbat_date'])
        doc['lines'][2]['text'] = 'OCTOBER16,2026 OCTOBER9,2026'
        self.assertIn('contradictory_header_dates', parse(doc)['issues'])

    def test_missing_origin_and_duplicate_ids_fail(self):
        doc = fixture()
        del doc['input_kind']
        with self.assertRaises(ValueError):
            parse(doc)
        doc = fixture()
        doc['lines'][1]['id'] = '0'
        with self.assertRaises(ValueError):
            parse(doc)

    def test_text_cannot_authenticate_admin(self):
        doc = fixture()
        doc['lines'][0]['text'] += ' Admin The Community Chat verified'
        out = parse(doc)
        self.assertEqual(out['source_verification']['status'], 'not_verified')
        self.assertFalse(out['automation_eligible'])


if __name__ == '__main__':
    unittest.main()

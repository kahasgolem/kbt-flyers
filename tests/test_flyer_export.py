import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from flyer_export import draft, override, regenerate, publication_values


def fixture(value='17:25'):
    # Synthetic verified-provider metadata tests the contract, not a calendar.
    return draft('2026-10-16', 'friday',
                 {'canonical_id': 'noach', 'provider': 'synthetic test provider', 'diaspora': True, 'verified': True, 'shabbat_date': '2026-10-17'},
                 {'noach': 'Noach'}, {'saturday_mincha': {'value': value, 'provenance': 'synthetic calculated default'}})


class ExportTests(unittest.TestCase):
    def test_override_survives_regeneration(self):
        old = override(fixture(), 'saturday_mincha', '17:30', 'Human intentional adjustment')
        old['fields']['saturday_mincha']['reviewed'] = True
        new = regenerate(old, fixture('17:20'))
        self.assertEqual(new['fields']['saturday_mincha']['override']['value'], '17:30')
        self.assertEqual(new['fields']['saturday_mincha']['default'], '17:20')
        self.assertFalse(new['fields']['saturday_mincha']['reviewed'])

    def test_unresolved_cannot_publish(self):
        doc = draft('2026-10-16')
        doc['fields']['parsha_display']['reviewed'] = True
        with self.assertRaises(ValueError):
            publication_values(doc, ['parsha_display'])
        doc = fixture()
        doc['fields']['saturday_arvit']['reviewed'] = True
        with self.assertRaises(ValueError):
            publication_values(doc, ['saturday_arvit'])

    def test_unreviewed_default_cannot_publish(self):
        with self.assertRaises(ValueError):
            publication_values(fixture(), ['saturday_mincha'])

    def test_spelling_and_header_choice(self):
        doc = fixture()
        self.assertEqual(doc['fields']['header_date']['default'], '2026-10-16')
        self.assertEqual(doc['fields']['saturday_date']['default'], '2026-10-17')
        self.assertEqual(doc['fields']['parsha_display']['default'], 'Noach')
        for key in ['header_date', 'parsha_display']:
            doc['fields'][key]['reviewed'] = True
        self.assertEqual(publication_values(doc, ['header_date', 'parsha_display'])['parsha_display'], 'Noach')
        self.assertEqual(draft('2026-10-16')['header_date_choice'], 'friday')
        self.assertEqual(draft('2026-10-16')['fields']['header_date']['default'], '2026-10-16')

    def test_stale_parsha_cannot_publish(self):
        metadata = fixture()['parsha']['calendar_evidence']
        doc = draft('2026-10-23', parsha=metadata, spellings={'noach': 'Noach'})
        self.assertFalse(doc['parsha']['verified'])

    def test_new_week_retains_override_but_requires_new_review(self):
        old = override(fixture(), 'saturday_mincha', '17:30', 'Human adjustment')
        old['fields']['saturday_mincha']['reviewed'] = True
        fresh = fixture()
        fresh['fields']['friday_date']['default'] = '2026-10-23'
        new = regenerate(old, fresh)
        self.assertEqual(new['fields']['saturday_mincha']['override']['value'], '17:30')
        self.assertFalse(new['fields']['saturday_mincha']['reviewed'])

    def test_parsha_requires_provider_and_diaspora(self):
        for metadata in [{}, {'canonical_id': 'noach', 'verified': True, 'provider': 'test'}]:
            doc = draft('2026-10-16', 'saturday', metadata, {'noach': 'Noach'})
            self.assertIsNone(doc['parsha']['canonical_id'])
            self.assertIsNone(doc['fields']['parsha_display']['default'])
        self.assertEqual(draft('2026-10-16', 'saturday')['fields']['header_date']['default'], '2026-10-17')

    def test_override_does_not_clear_contradiction(self):
        doc = fixture()
        doc['fields']['saturday_mincha']['issues'] = ['conflicting_provider_inputs']
        doc = override(doc, 'saturday_mincha', '17:30', 'Human edit')
        doc['fields']['saturday_mincha']['reviewed'] = True
        with self.assertRaises(ValueError):
            publication_values(doc, ['saturday_mincha'])


if __name__ == '__main__':
    unittest.main()

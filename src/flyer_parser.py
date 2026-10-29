"""Offline rule prototype. Accepts section-aware text evidence, never image bytes.

No network, OCR, WhatsApp connection, or automation is performed here.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
import sys

SECTIONS = {
    'erev shabbat': 'erev_shabbat', 'shabbat morning': 'shabbat_morning',
    'shabbat afternoon': 'shabbat_afternoon', 'sunday': 'sunday',
    'monday-friday': 'monday_friday', 'shiurim': 'shiurim',
}
SPECIAL = re.compile(r'\b(rosh\s+hashanah|yom\s+kippur|sukk?ot|sukk?oth|shemini\s+atzeret|simchat\s+torah|pesach|passover|shavuot|fast\s+day|tzom|tisha\s+b.?av|yom\s+tov|chagim)\b', re.I)
TIME = re.compile(r'(?<![\d:])(\d{1,2}):(\d{2})(?:\s*([ap])\.?m\.?)?(?!\d)', re.I)
DATE = re.compile(r'\b(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s*(\d{1,2})\s*,?\s*(\d{4})\b', re.I)
MONTHS = {m: i + 1 for i, m in enumerate('JANUARY FEBRUARY MARCH APRIL MAY JUNE JULY AUGUST SEPTEMBER OCTOBER NOVEMBER DECEMBER'.split())}


def normalized(text):
    return re.sub(r'\s*-\s*', '-', re.sub(r'\s+', ' ', text.replace('–', '-').replace('—', '-'))).strip().casefold()


def section_heading(text):
    key = normalized(text)
    if key in SECTIONS:
        return SECTIONS[key]
    # OCR may recognize a decorative icon before a heading. Keep evidence intact;
    # permit only the observed nonword icon token, never arbitrary prefix text.
    if key == 'i-li shabbat afternoon':
        return 'shabbat_afternoon'
    return None


def validate_input(doc):
    if doc.get('input_kind') not in ('synthetic', 'manual_transcription', 'local_ocr'):
        raise ValueError('input_kind must explicitly identify evidence origin')
    if not isinstance(doc.get('document_id'), str) or not doc['document_id']:
        raise ValueError('document_id is required')
    if not isinstance(doc.get('lines'), list):
        raise ValueError('lines must be an array')
    ids = set()
    for line in doc['lines']:
        if not isinstance(line.get('id'), str) or line['id'] in ids:
            raise ValueError('line ids must be unique strings')
        ids.add(line['id'])
        if not isinstance(line.get('text'), str):
            raise ValueError('line text must be a string')
        if not isinstance(line.get('region'), str) or not line['region']:
            raise ValueError('explicit region required; do not flatten multiple columns')
        box = line.get('bbox')
        if box is not None and (not isinstance(box, list) or len(box) != 4 or
                               any(type(v) not in (float, int) or v < 0 for v in box)):
            raise ValueError('bbox must be null or [x,y,width,height] in original-image pixels')


def category(label, section):
    if re.search(r'candle|shema|gr["”]?a|shkiyah|rabbeinu tam|sunset|sunrise|havdalah|shabbat ends|deadline', label, re.I):
        return 'zman_deadline'
    if section == 'shiurim' or re.search(r'shiur|class|seudah|seuda|lecture|hilchot|program|shir hashirim', label, re.I):
        return 'class_event'
    if re.search(r'shacharit|shaharit|mincha|minha|arvit|maariv|musaf|kabbalat|minyan|hodu', label, re.I):
        return 'service'
    return 'unknown'


def parse(doc):
    validate_input(doc)
    lines = copy.deepcopy(doc['lines'])
    full = '\n'.join(x['text'] for x in lines)
    anchors = {section_heading(x['text']) for x in lines if section_heading(x['text'])}
    identity = bool(re.search(r'kehilat\s+bnei\s+torah', full, re.I))
    title = bool(re.search(r'\bparshat\s+\w+', full, re.I))
    special = bool(SPECIAL.search(full))
    weekly = identity and title and set(SECTIONS.values()) <= anchors
    classification = 'unsupported_special' if special else ('weekly_candidate' if weekly else 'unknown')
    issues = ['offline_prototype_requires_review', 'source_not_authenticated']
    if doc['input_kind'] != 'local_ocr':
        issues.append('not_automatic_ocr')
    if any(x.get('bbox') is None for x in lines):
        issues.append('missing_image_coordinates')
    dates = set()
    date_evidence = []
    for line in lines:
        if line['region'] != 'header':
            continue
        for match in DATE.finditer(line['text']):
            date_evidence.append(line['id'])
            try:
                dates.add(dt.date(int(match[3]), MONTHS[match[1].upper()], int(match[2])))
            except ValueError:
                issues.append('invalid_header_date')
    friday = next(iter(dates)) if len(dates) == 1 else None
    if len(dates) > 1:
        issues.append('contradictory_header_dates')
    if friday and friday.weekday() != 4:
        issues.append('header_date_not_friday')
        friday = None
    if not friday:
        issues.append('unresolved_friday_anchor')
    address = bool(re.search(r'9017\s*w\.?\s*pico\s*blvd', full, re.I))
    timezone = {'value': 'America/Los_Angeles' if address else None,
                'provenance': 'inferred_from_9017_W_Pico_Blvd_LA' if address else 'unresolved',
                'verified': False}
    issues.append('timezone_inferred_requires_confirmation' if address else 'timezone_unresolved')
    result = {'schema_version': '0.1', 'document_id': doc['document_id'],
              'input_kind': doc['input_kind'], 'classification': classification,
              'confidence': {'level': 'unvalidated_rule_match', 'score': None},
              'review_required': True, 'automation_eligible': False,
              'source_verification': {'status': 'not_verified', 'group_jid': None,
                                      'sender_jid': None, 'admin_at_message_time': None},
              'friday_date': friday.isoformat() if friday else None,
              'shabbat_date': (friday + dt.timedelta(days=1)).isoformat() if friday else None,
              'date_evidence_line_ids': date_evidence, 'timezone': timezone,
              'issues': issues, 'evidence_lines': lines, 'entries': [], 'unparsed_line_ids': []}
    if classification != 'weekly_candidate':
        issues.append('unsupported_special_layout' if special else 'missing_weekly_anchors')
        return result
    # Only consume order within an explicitly supplied region. Never use global
    # reading order to carry a heading between columns.
    active = {}
    seen = {}
    for line in lines:
        text = line['text']
        key = normalized(text)
        region = line['region']
        if region.startswith('unstructured_'):
            result['unparsed_line_ids'].append(line['id'])
            continue
        heading = section_heading(text)
        if heading:
            active[region] = (heading, line['id'])
            continue
        if region == 'header':
            continue
        section, heading_id = active.get(region, (None, None))
        if section is None:
            result['unparsed_line_ids'].append(line['id'])
            continue
        matches = list(TIME.finditer(text))
        cat = category(text, section)
        if not matches and cat == 'unknown':
            result['unparsed_line_ids'].append(line['id'])
            continue
        warnings = []
        if len(matches) > 1:
            warnings.append('multiple_times_unresolved')
        printed = matches[0].group() if len(matches) == 1 else None
        value = None
        if printed:
            m = matches[0]
            hour, minute = int(m[1]), int(m[2])
            if not 0 <= minute <= 59 or not 1 <= hour <= 12:
                warnings.append('invalid_or_unsupported_time')
            elif not m[3]:
                warnings.append('meridiem_unresolved')
            else:
                value = f'{hour % 12 + (12 if m[3].lower() == "p" else 0):02d}:{minute:02d}'
        if not matches:
            warnings.append('untimed_entry')
        label = TIME.sub('', text).strip(' .:-')
        if cat == 'unknown':
            warnings.append('unknown_category')
        offset = {'erev_shabbat': 0, 'shabbat_morning': 1, 'shabbat_afternoon': 1}.get(section)
        day = (friday + dt.timedelta(days=offset)).isoformat() if friday and offset is not None else None
        if section in ('sunday', 'monday_friday', 'shiurim'):
            warnings.append('calendar_applicability_unresolved')
        entry = {'id': line['id'], 'label': label, 'section': section, 'category': cat,
                 'original_text': text, 'printed_time': printed, 'normalized_time': value,
                 'all_printed_times': [m.group() for m in matches],
                 'correction': None, 'date': day,
                 'applicability': {'printed_section': section, 'resolved_date': day,
                                   'basis': 'friday_header_plus_section_day' if day else 'unresolved'},
                 'evidence_line_ids': [heading_id, line['id']],
                 'bbox': line.get('bbox'), 'confidence': 'unvalidated_rule_match',
                 'review_required': True, 'issues': warnings}
        duplicate_key = (section, normalized(label))
        if duplicate_key in seen and seen[duplicate_key]['normalized_time'] != value:
            warnings.append('contradictory_duplicate_time')
            seen[duplicate_key]['issues'].append('contradictory_duplicate_time')
        seen[duplicate_key] = entry
        result['entries'].append(entry)
    if result['unparsed_line_ids']:
        issues.append('unparsed_content')
    return result


def record_source_error(extraction, entry_id, provenance, corrected_time=None):
    """Human review only; retain extraction unchanged and append separate provenance."""
    if not isinstance(provenance, str) or not provenance.strip():
        raise ValueError('human review provenance required')
    if corrected_time is not None and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', corrected_time):
        raise ValueError('correction must be HH:MM or null')
    result = copy.deepcopy(extraction)
    entry = next((x for x in result['entries'] if x['id'] == entry_id), None)
    if entry is None:
        raise ValueError('unknown entry id')
    entry['issues'].append('user_confirmed_source_error')
    entry['correction'] = {'normalized_time': corrected_time, 'provenance': provenance,
                           'status': 'value_supplied' if corrected_time else 'awaiting_correct_time'}
    return result


if __name__ == '__main__':
    # One explicitly selected JSON document in, one JSON extraction out.
    with open(sys.argv[1], encoding='utf-8') as handle:
        print(json.dumps(parse(json.load(handle)), indent=2, ensure_ascii=False))

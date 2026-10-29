"""Provider-neutral editable flyer data. No calendar lookup or publishing I/O."""
import copy
import datetime as dt

SCHEDULE_FIELDS = (
    'friday_shkiyah', 'candles_display', 'friday_mincha_arvit', 'shir_hashirim',
    'shema_mga', 'shema_gra', 'early_minyan', 'hilchot_first', 'hodu',
    'hilchot_second', 'boys_program', 'shiur', 'saturday_mincha',
    'seudah_shlishi', 'saturday_sunset', 'saturday_arvit', 'shabbat_ends',
    'rabbeinu_tam', 'sunday_shacharit', 'sunday_mincha_arvit',
    'sunday_late_arvit', 'monday_thursday_shacharit_early',
    'monday_thursday_shacharit_later', 'monday_thursday_mincha_arvit',
    'monday_thursday_late_arvit',
)


def field(value=None, provenance=None):
    return {'default': value, 'default_provenance': provenance, 'override': None,
            'reviewed': False, 'issues': ['unresolved'] if value is None else []}


def draft(friday_date=None, header_date_choice='friday', parsha=None, spellings=None, schedule=None):
    """parsha is supplied calendar evidence, not inferred from Gregorian date.

    parsha: {canonical_id, provider, diaspora, verified, shabbat_date}. Spelling map is keyed
    by canonical_id and controlled by the user (e.g. Sephardic spellings).
    Each schedule value: {value, provenance, issues?}; defaults need human review.
    """
    if header_date_choice not in (None, 'friday', 'saturday'):
        raise ValueError('header_date_choice must be explicit friday/saturday or null')
    friday = dt.date.fromisoformat(friday_date) if friday_date else None
    if friday and friday.weekday() != 4:
        raise ValueError('friday_date must be Friday')
    parsha = copy.deepcopy(parsha or {})
    verified = (parsha.get('verified') is True and bool(parsha.get('provider'))
                and type(parsha.get('diaspora')) is bool and bool(parsha.get('canonical_id'))
                and friday is not None
                and parsha.get('shabbat_date') == (friday + dt.timedelta(days=1)).isoformat())
    canonical = parsha.get('canonical_id') if verified else None
    display = (spellings or {}).get(canonical) if canonical else None
    fields = {
        'friday_date': field(friday.isoformat() if friday else None, 'supplied civil Friday anchor'),
        'saturday_date': field((friday + dt.timedelta(days=1)).isoformat() if friday else None, 'Friday plus one civil day'),
        'header_date': field(None, 'explicit header_date_choice required'),
        'parsha_display': field(display, 'configurable user spelling map; verified calendar evidence required'),
    }
    if header_date_choice:
        fields['header_date'] = field(fields[header_date_choice + '_date']['default'], 'explicit choice: ' + header_date_choice)
    schedule = schedule or {}
    if set(schedule) - set(SCHEDULE_FIELDS):
        raise ValueError('unknown schedule field; extend contract explicitly')
    for key in SCHEDULE_FIELDS:
        item = schedule.get(key, {})
        fields[key] = field(item.get('value'), item.get('provenance'))
        fields[key]['issues'].extend(item.get('issues', []))
        if item.get('value') is not None and not item.get('provenance'):
            fields[key]['issues'].append('missing_provenance')
    return {'contract_version': '1', 'header_date_choice': header_date_choice,
            'header_policy_provenance': 'User confirmed Friday publication date; parsha belongs to following Shabbat',
            'parsha': {'canonical_id': canonical, 'calendar_evidence': parsha,
                       'verified': verified, 'spelling_map': copy.deepcopy(spellings or {})},
            'fields': fields, 'publication_enabled': False}


def override(doc, key, value, provenance):
    """Preserve a human edit separately; review is explicit even after an edit."""
    if value is None or not provenance:
        raise ValueError('override needs a non-null value and human provenance')
    out = copy.deepcopy(doc)
    out['fields'][key]['override'] = {'value': value, 'provenance': provenance}
    out['fields'][key]['reviewed'] = False
    return out


def regenerate(previous, fresh):
    """New defaults cannot erase edits; invalidates review when default changes."""
    out = copy.deepcopy(fresh)
    same_context = (previous['fields']['friday_date']['default'] == fresh['fields']['friday_date']['default']
                    and previous['parsha'] == fresh['parsha']
                    and previous['header_date_choice'] == fresh['header_date_choice'])
    for key, new in out['fields'].items():
        old = previous['fields'].get(key)
        if not old:
            continue
        new['override'] = copy.deepcopy(old['override'])
        if same_context and new['default'] == old['default'] and new['default_provenance'] == old['default_provenance'] and new['issues'] == old['issues']:
            new['reviewed'] = old['reviewed']
    return out


def publication_values(doc, selected_fields):
    """Local fail-closed rendering gate, NOT a network publishing operation.

    Every selected field needs review. Overrides resolve absent defaults only;
    contradictions/other issues require resolution in the source data contract.
    """
    if not selected_fields:
        raise ValueError('explicit template field selection required')
    blockers = []
    values = {}
    if doc['header_date_choice'] not in ('friday', 'saturday'):
        blockers.append('header_date_choice_unresolved')
    if not doc['parsha']['verified']:
        blockers.append('parsha_calendar_unverified')
    for key in selected_fields:
        item = doc['fields'][key]
        value = item['override']['value'] if item['override'] else item['default']
        remaining = [issue for issue in item['issues'] if not (item['override'] and issue == 'unresolved')]
        if value is None or not item['reviewed'] or remaining:
            blockers.append(key)
        values[key] = copy.deepcopy(value)
    if blockers:
        raise ValueError('publication blocked: ' + ', '.join(blockers))
    return values

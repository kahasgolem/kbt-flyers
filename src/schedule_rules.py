"""User-supplied schedule arithmetic, without astronomical calculation or I/O.

Inputs are timezone-aware ISO timestamps from an explicitly identified provider.
The caller supplies the event's Los Angeles civil date and UTC offset. Explicit
offset checking avoids depending on a separately installed IANA tzdata package.
These contemporary US DST rules support years 2007 onward only.
"""
import datetime as dt


def la_offset(day):
    if day.year < 2007:
        raise ValueError('Los Angeles dates before 2007 are unsupported')
    march = dt.date(day.year, 3, 1)
    november = dt.date(day.year, 11, 1)
    start = march + dt.timedelta(days=(6 - march.weekday()) % 7 + 7)
    end = november + dt.timedelta(days=(6 - november.weekday()) % 7)
    return dt.timedelta(hours=-7 if start <= day < end else -8)


def raw(value, day, provenance):
    if not provenance or not isinstance(provenance, str):
        raise ValueError('explicit provider/settings provenance required')
    stamp = dt.datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('raw timestamp must include UTC offset')
    # Astronomical inputs are daytime/evening events, not transition-hour events.
    local = stamp.astimezone(dt.timezone(la_offset(day)))
    if local.date() != day:
        raise ValueError('astronomical input does not fall on requested LA date')
    return local


def rounded(stamp, minutes=1, direction='floor'):
    if minutes not in (1, 5) or direction not in ('floor', 'ceil'):
        raise ValueError('unsupported rounding')
    origin = stamp.replace(hour=0, minute=0, second=0, microsecond=0)
    quantum = minutes * 60 * 1000000
    elapsed = stamp - origin
    micros = (elapsed.seconds + elapsed.days * 86400) * 1000000 + elapsed.microseconds
    count = micros // quantum if direction == 'floor' else -(-micros // quantum)
    return origin + dt.timedelta(microseconds=count * quantum)


def calculate(friday, inputs, provenance, arvit_uses_8_5=None):
    """Return independent expectations. Missing/unknown methods stay unresolved.

    inputs: friday_sunset, saturday_sunset, tzeit_8_5, shema_mga, shema_gra.
    Rabbeinu Tam is intentionally unresolved until its method is specified.
    No supplied value is invented, fetched, or treated as an OCR correction.
    """
    friday = dt.date.fromisoformat(friday)
    if friday.weekday() != 4:
        raise ValueError('anchor must be a Friday')
    saturday = friday + dt.timedelta(days=1)
    sunday = friday + dt.timedelta(days=2)
    if not isinstance(provenance, str) or not provenance.strip():
        raise ValueError('provider/settings provenance required')
    result = {'timezone': 'America/Los_Angeles', 'provider_provenance': provenance,
              'friday_date': friday.isoformat(), 'review_required': True,
              'expectations': {}}
    es = result['expectations']

    def put(key, stamp, rule, reason=None):
        es[key] = {'calculated': stamp.isoformat() if stamp else None,
                   'rule': rule, 'unresolved_reason': reason,
                   'provenance': 'user_supplied_rules; ' + provenance}

    def fixed(key, day, hour, minute):
        put(key, dt.datetime.combine(day, dt.time(hour, minute), dt.timezone(la_offset(day))), 'user_fixed_time')

    def get(key, day):
        return raw(inputs[key], day, provenance) if inputs.get(key) else None

    fs = get('friday_sunset', friday)
    candles = fs - dt.timedelta(minutes=18) if fs else None
    fm = min(rounded(candles, 5), dt.datetime.combine(friday, dt.time(18, 30), dt.timezone(la_offset(friday)))) if candles else None
    put('friday_shkiyah', rounded(fs) if fs else None, 'floor raw sunset to minute', 'missing sunset' if not fs else None)
    put('candles_raw', candles, 'raw sunset minus 18 minutes', 'missing sunset' if not fs else None)
    put('candles_display', None, 'not defined', 'candle display rounding unconfirmed')
    put('friday_mincha_arvit', fm, 'floor raw candles to 5 minutes; cap 18:30', 'missing sunset' if not fs else None)
    put('shir_hashirim', fm - dt.timedelta(minutes=15) if fm else None, 'scheduled Friday Mincha minus 15 minutes', 'missing sunset' if not fs else None)
    for k in ('shema_mga', 'shema_gra', 'saturday_sunset'):
        value = get(k, saturday)
        put(k, rounded(value) if value else None, 'floor supplied raw timestamp to minute', 'missing raw input' if not value else None)
    tz = get('tzeit_8_5', saturday)
    sm = rounded(tz - dt.timedelta(minutes=90), 5, 'ceil') if tz else None
    for key, delta in [('saturday_mincha', 0), ('hilchot_second', 90), ('boys_program', 60), ('shiur', 60)]:
        put(key, sm - dt.timedelta(minutes=delta) if sm else None,
            'ceil(raw 8.5 degree tzeit minus 90 minutes) to 5 minutes' if not delta else f'scheduled Saturday Mincha minus {delta} minutes',
            'missing raw 8.5 degree tzeit' if not tz else None)
    put('shabbat_ends', rounded(tz, 1, 'ceil') if tz else None, 'ceil raw 8.5 degree tzeit to minute', 'missing tzeit' if not tz else None)
    put('saturday_arvit', rounded(tz, 5) if tz and arvit_uses_8_5 is True else None,
        'floor raw 8.5 degree tzeit to 5 minutes',
        None if tz and arvit_uses_8_5 is True else 'Arvit tzeit definition unconfirmed or input missing')
    put('rabbeinu_tam', None, 'ceil to minute after method is confirmed', 'underlying method unconfirmed')
    put('seudah_shlishi', None, 'untimed after scheduled Mincha', 'intentionally untimed')
    fixed('early_minyan', saturday, 8, 0)
    fixed('hilchot_first', saturday, 8, 15)
    fixed('hodu', saturday, 8, 45)
    fixed('sunday_shacharit', sunday, 8, 15)
    for offset in range(2, 7):  # Sunday through Thursday following this Shabbat.
        day = friday + dt.timedelta(days=offset)
        name = ('sunday', 'monday', 'tuesday', 'wednesday', 'thursday')[offset - 2]
        fixed(name + '_late_arvit', day, 21, 30)
        copied = dt.datetime.combine(day, fm.time(), dt.timezone(la_offset(day))) if fm else None
        put(name + '_mincha_arvit', copied, 'same wall-clock time as Friday', 'missing Friday calculation' if not fm else None)
        if offset >= 3:
            fixed(name + '_shacharit_early', day, 6, 45)
            fixed(name + '_shacharit_later', day, 8, 25)
    put('friday_morning', None, 'not specified', 'Friday morning schedule unspecified')
    result['weekday_applicability'] = 'calculation scenario uses Sunday–Thursday after anchored Shabbat; flyer applicability still requires confirmation'
    return result


def compare(printed_hhmm, expectation, user_correction=None):
    """Compare a printed minute against calculated time; never mutate extraction."""
    calculated = expectation['calculated']
    gap = None
    severity = 'unresolved'
    if printed_hhmm is None or calculated is None:
        status = 'unresolved'
    else:
        # Validate printed input before comparison, with no meridiem inference.
        import re
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', printed_hhmm):
            raise ValueError('printed value must be normalized HH:MM')
        stamp = dt.datetime.fromisoformat(calculated)
        status = 'match' if printed_hhmm == stamp.strftime('%H:%M') and stamp.second == stamp.microsecond == 0 else 'mismatch'
        hours, minutes = map(int, printed_hhmm.split(':'))
        gap = abs((stamp.replace(hour=hours, minute=minutes, second=0, microsecond=0) - stamp).total_seconds()) / 60
        severity = 'match' if gap == 0 else ('potential_error' if gap > 5 else 'discrepancy')
    return {'printed': printed_hhmm, 'calculated': calculated,
            'user_correction': user_correction, 'status': status,
            'review_required': True, 'calculation_provenance': expectation['provenance'],
            'absolute_gap_minutes': gap, 'severity': severity,
            'interpretation': 'A discrepancy may be an intentional adjustment; never auto-correct.'}


def mincha_from_rounded_end(end):
    """Bounds implied by ceil-to-minute end, not a fabricated raw tzeit.

    Raw tzeit is (end minus one minute, end]; returns every possible scheduled
    Mincha at the 5-minute ceiling. End must be an aware exact-minute timestamp.
    """
    stamp = dt.datetime.fromisoformat(end)
    if stamp.tzinfo is None or stamp.second or stamp.microsecond:
        raise ValueError('aware minute-aligned end required')
    lower = stamp - dt.timedelta(minutes=1)
    first = rounded(lower + dt.timedelta(microseconds=1) - dt.timedelta(minutes=90), 5, 'ceil')
    last = rounded(stamp - dt.timedelta(minutes=90), 5, 'ceil')
    return {'raw_tzeit_lower_exclusive': lower.isoformat(), 'raw_tzeit_upper_inclusive': stamp.isoformat(),
            'possible_mincha': sorted({first.isoformat(), last.isoformat()})}

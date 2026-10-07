"""Explicit notation data -> LilyPond score and parts. Standard library only.

No transcription, performance quantization, plugin execution or implicit
articulation/phrase inference. Unsupported notation is rejected.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from music_data import load_json

STEPS = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)
DYNAMICS = {'pppp', 'ppp', 'pp', 'p', 'mp', 'mf', 'f', 'ff', 'fff', 'ffff', 'sfz', 'fp'}
ARTS = {'staccato': '-.', 'tenuto': '--', 'accent': '->', 'marcato': '-^'}
CLEFS = {'treble', 'alto', 'tenor', 'bass', 'treble_8', 'treble^8', 'bass_8'}


def keys(obj, allowed, label):
    if not isinstance(obj, dict):
        raise ValueError(f'{label} must be an object')
    extra = set(obj) - set(allowed.split())
    if extra:
        raise ValueError(f'Unknown {label} fields: {sorted(extra)}')


def integer(n, low, high, label):
    if type(n) is not int or not low <= n <= high:
        raise ValueError(f'Invalid {label}')
    return n


def rational(value, label='time'):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f'Invalid {label}')
    try:
        f = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        raise ValueError(f'Invalid {label}') from None
    # Exact dyadic notation only; no silent rounding or inferred tuplets.
    if f.denominator > 16 or f.denominator & (f.denominator - 1):
        raise ValueError(f'{label} needs explicit rhythmic adaptation: {value}')
    return f


def ly_string(value):
    if not isinstance(value, str) or len(value) > 500 or any(ord(c) < 32 for c in value):
        raise ValueError('Expected a short, single-line text string')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def pitch(p):
    keys(p, 'step alter octave', 'pitch')
    if p['step'] not in STEPS:
        raise ValueError('Invalid pitch step')
    alter = integer(p['alter'], -2, 2, 'alteration')
    octave = integer(p['octave'], -1, 9, 'octave')
    midi = 12 * (octave + 1) + STEPS[p['step']] + alter
    if not 0 <= midi <= 127:
        raise ValueError('Pitch outside MIDI range')
    name = p['step'].lower() + ('is' * alter if alter > 0 else 'es' * -alter)
    name += "'" * max(0, octave - 3) + ',' * max(0, 3 - octave)
    return name, midi


def key_command(k):
    keys(k, 'step alter mode', 'key')
    name, _ = pitch(dict(step=k['step'], alter=k['alter'], octave=3))
    if k['mode'] not in ('major', 'minor'):
        raise ValueError('Only explicit major/minor signatures are supported')
    return f'\\key {name} \\{k["mode"]}'


def _validate_v1(data, part_limit=64):
    keys(data, 'schema_version kind title subtitle composer font bars parts provenance', 'notation')
    if type(data['schema_version']) is not int or data['schema_version'] != 1 or data['kind'] != 'notation':
        raise ValueError('Expected notation schema version 1')
    for field in ('title', 'subtitle', 'composer', 'font'):
        if field in data:
            ly_string(data[field])
    bars = data['bars']
    if not isinstance(bars, list) or not 1 <= len(bars) <= 10000:
        raise ValueError('Expected 1..10000 bars')
    times = [Fraction(0)]
    meter = None
    for i, bar in enumerate(bars):
        keys(bar, 'meter key tempo rehearsal text', 'bar')
        if 'meter' in bar:
            meter = bar['meter']
            if not isinstance(meter, list) or len(meter) != 2:
                raise ValueError('Invalid meter')
            integer(meter[0], 1, 32, 'meter numerator')
            if type(meter[1]) is not int or meter[1] not in (1, 2, 4, 8, 16):
                raise ValueError('Invalid meter denominator')
        if meter is None or i == 0 and ('key' not in bar or 'tempo' not in bar):
            raise ValueError('First bar needs meter, key and tempo')
        if 'key' in bar:
            key_command(bar['key'])
        if 'tempo' in bar:
            integer(bar['tempo'], 1, 1000, 'quarter-note tempo')
        for field in ('rehearsal', 'text'):
            if field in bar:
                ly_string(bar[field])
        times.append(times[-1] + Fraction(4 * meter[0], meter[1]))
    parts = data['parts']
    if not isinstance(parts, list) or not 1 <= len(parts) <= part_limit:
        raise ValueError(f'Expected 1..{part_limit} pitched single-staff parts')
    ids = set()
    counts = []
    for part in parts:
        keys(part, 'id name short_name clef notes breaks page_breaks', 'part')
        ident = part['id']
        if (not isinstance(ident, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', ident)
                or ident in ids or ident in {'score', 'audit', 'music', 'notation', 'engraving-report'}):
            raise ValueError('Part IDs must be unique safe identifiers')
        ids.add(ident)
        ly_string(part['name']); ly_string(part['short_name'])
        if part['clef'] not in CLEFS:
            raise ValueError('Unsupported clef')
        for field in ('breaks', 'page_breaks'):
            for bar in part.get(field, []):
                integer(bar, 1, len(bars) - 1, field)
        if not isinstance(part['notes'], list) or len(part['notes']) > 200000:
            raise ValueError('Invalid note list')
        end, slur, hairpin = Fraction(0), False, False
        note_ids = set()
        for n in part['notes']:
            keys(n, 'id beat duration pitches articulations dynamic text slur_start slur_end hairpin hairpin_stop', 'note')
            if not isinstance(n['id'], str) or n['id'] in note_ids:
                raise ValueError('Note IDs must be unique strings within each part')
            note_ids.add(n['id'])
            start = rational(n['beat'], 'note beat')
            duration = rational(n['duration'], 'note duration')
            if start < end or duration <= 0 or start + duration > times[-1]:
                raise ValueError(f'Overlap, order or extent error in {ident}/{n["id"]}')
            end = start + duration
            if not isinstance(n['pitches'], list) or not 1 <= len(n['pitches']) <= 12:
                raise ValueError('Expected 1..12 simultaneous pitches')
            pitches = [pitch(p)[1] for p in n['pitches']]
            if len(set(pitches)) != len(pitches):
                raise ValueError('Duplicate chord pitch')
            for art in n.get('articulations', []):
                if art not in ARTS:
                    raise ValueError('Unsupported articulation')
            if 'dynamic' in n and n['dynamic'] not in DYNAMICS:
                raise ValueError('Unsupported dynamic')
            if 'text' in n:
                ly_string(n['text'])
            for flag in ('slur_start', 'slur_end', 'hairpin_stop'):
                if flag in n and type(n[flag]) is not bool:
                    raise ValueError(f'{flag} must be boolean')
            if n.get('slur_start'):
                if slur:
                    raise ValueError('Nested slur')
                slur = True
            if n.get('slur_end'):
                if not slur:
                    raise ValueError('Slur end without start')
                slur = False
            if n.get('hairpin_stop') or 'dynamic' in n:
                hairpin = False
            if 'hairpin' in n:
                if n['hairpin'] not in ('<', '>') or hairpin:
                    raise ValueError('Invalid or overlapping hairpin')
                hairpin = True
        if slur or hairpin:
            raise ValueError(f'Unclosed slur or hairpin in {ident}')
        counts.append(dict(id=ident, events=len(part['notes']),
                           pitches=sum(len(n['pitches']) for n in part['notes'])))
    return times, counts


def safe_id(value, seen, label):
    if (not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', value)
            or value in seen):
        raise ValueError(f'{label} IDs must be unique safe identifiers')
    seen.add(value)


def notation_voices(data):
    """Stable musical identities, independent of MIDI channels or staff count."""
    for part in data['parts']:
        if data['schema_version'] == 1:
            yield dict(id=part['id'], part_id=part['id'], notes=part['notes'], clef=part['clef'])
        else:
            for staff in part['staves']:
                for voice in staff['voices']:
                    yield dict(id='/'.join((part['id'], staff['id'], voice['id'])),
                               part_id=part['id'], staff_id=staff['id'], voice_id=voice['id'],
                               notes=voice['notes'], clef=staff['clef'])


def validate_lane(events, end, pedal=False):
    if not isinstance(events, list) or len(events) > 200000:
        raise ValueError('Invalid pedal or dynamics event list')
    previous, active = Fraction(-1), False
    for e in events:
        keys(e, 'beat action' if pedal else 'beat dynamic hairpin hairpin_stop text', 'pedal' if pedal else 'dynamics')
        beat = rational(e['beat'], 'direction beat')
        if not previous < beat <= end or beat < 0:
            raise ValueError('Direction events must have unique ordered beats inside the music')
        previous = beat
        if pedal:
            action = e['action']
            if action == 'down' and not active and beat < end:
                active = True
            elif action == 'up' and active:
                active = False
            elif action == 'change' and active and beat < end:
                pass
            else:
                raise ValueError('Invalid sustain pedal transition; use down, change, up')
        else:
            if len(e) == 1:
                raise ValueError('Empty dynamics event')
            if 'dynamic' in e and e['dynamic'] not in DYNAMICS:
                raise ValueError('Unsupported dynamic')
            if 'hairpin_stop' in e and type(e['hairpin_stop']) is not bool:
                raise ValueError('hairpin_stop must be boolean')
            if 'text' in e:
                ly_string(e['text'])
            if e.get('hairpin_stop') or 'dynamic' in e:
                active = False
            if 'hairpin' in e:
                if e['hairpin'] not in ('<', '>') or active or beat == end:
                    raise ValueError('Invalid or overlapping hairpin')
                active = True
    if active:
        raise ValueError('Unclosed sustain pedal' if pedal else 'Unclosed dynamics hairpin')


def validate(data):
    if not isinstance(data, dict) or data.get('schema_version') != 2:
        return _validate_v1(data)
    if type(data['schema_version']) is not int:
        raise ValueError('Expected integer notation schema version')
    parts = data['parts']
    if not isinstance(parts, list) or not 1 <= len(parts) <= 64:
        raise ValueError('Expected 1..64 instrumental parts')
    part_ids, flat, counts = set(), [], []
    for part in parts:
        keys(part, 'id name short_name group staves dynamics pedal breaks page_breaks', 'part')
        safe_id(part['id'], part_ids, 'Part')
        if part['id'] in {'score', 'audit', 'music', 'notation', 'engraving-report'}:
            raise ValueError('Reserved part ID')
        ly_string(part['name']); ly_string(part['short_name'])
        staves = part['staves']
        group = part.get('group', 'staff')
        required = 2 if group == 'piano' else 1
        if group not in ('staff', 'piano') or not isinstance(staves, list) or len(staves) != required:
            raise ValueError('Use group=piano with two staves, or group=staff with one')
        staff_ids, voices_count = set(), 0
        for staff in staves:
            keys(staff, 'id clef voices', 'staff')
            safe_id(staff['id'], staff_ids, 'Staff')
            voices = staff['voices']
            if not isinstance(voices, list) or not 1 <= len(voices) <= 4:
                raise ValueError('Each staff supports 1..4 independent voices')
            voice_ids, numbers = set(), set()
            for index, voice in enumerate(voices):
                keys(voice, 'id notes voice_number', 'voice')
                safe_id(voice['id'], voice_ids, 'Voice')
                number = integer(voice.get('voice_number', index + 1), 1, 4, 'voice_number')
                if number in numbers:
                    raise ValueError('Duplicate voice_number in staff')
                numbers.add(number)
                # Reuse the existing sequential-note validator for each voice.
                # Overlap is allowed between voices and rejected within a voice.
                flat.append(dict(id=f'voice-{len(flat)}', name=part['name'], short_name=part['short_name'],
                                 clef=staff['clef'], notes=voice['notes'],
                                 **{k: part[k] for k in ('breaks', 'page_breaks') if k in part}))
                voices_count += 1
        counts.append(dict(id=part['id'], staves=len(staves), voices=voices_count))
    surrogate = {**data, 'schema_version': 1, 'parts': flat}
    times, voice_counts = _validate_v1(surrogate, part_limit=512)
    cursor = 0
    for part, count in zip(parts, counts):
        current = voice_counts[cursor:cursor + count['voices']]
        count.update(events=sum(v['events'] for v in current), pitches=sum(v['pitches'] for v in current))
        cursor += count['voices']
        validate_lane(part.get('dynamics', []), times[-1])
        validate_lane(part.get('pedal', []), times[-1], pedal=True)
    return times, counts


def duration_token(d):
    for denominator in (1, 2, 4, 8, 16, 32, 64):
        base = Fraction(4, denominator)
        if d == base:
            return str(denominator)
        if d == base * Fraction(3, 2):
            return str(denominator) + '.'
    raise ValueError(f'Unrepresentable duration {d}')


def split_rhythm(offset, duration, rest=False):
    """Split at clear simple-meter beat boundaries; retain explicit dotted notes."""
    candidates = sorted({Fraction(4, d) * mult
                         for d in (1, 2, 4, 8, 16, 32, 64)
                         for mult in ((1,) if rest else (1, Fraction(3, 2)))}, reverse=True)
    pieces = []
    while duration:
        for d in candidates:
            if d > duration:
                continue
            if offset.denominator != 1 and d > (offset.numerator // offset.denominator + 1 - offset):
                continue
            base = d if d.numerator == 1 or d.denominator == 1 and d in (1, 2, 4) else d * Fraction(2, 3)
            # A duration must align with its undotted value; e.g. an offbeat
            # dotted quarter becomes an eighth tied to a quarter.
            if offset % base == 0:
                pieces.append(d)
                offset += d; duration -= d
                break
        else:
            raise ValueError('Rhythm requires unsupported notation')
    return pieces


def variable(index):
    # LilyPond variable names use letters only.
    return 'music' + chr(65 + index // 26) + chr(65 + index % 26)


def format_part(part, times, with_decoration=True):
    bar_tokens = [[] for _ in times[:-1]]
    audit = []
    previous = Fraction(0)
    sequence = []
    for n in part['notes']:
        start = rational(n['beat'])
        if start > previous:
            sequence.append((previous, start - previous, None))
        duration = rational(n['duration'])
        sequence.append((start, duration, n))
        previous = start + duration
    if previous < times[-1]:
        sequence.append((previous, times[-1] - previous, None))
    bi = 0
    for start, duration, n in sequence:
        while bi + 1 < len(times) and start >= times[bi + 1]:
            bi += 1
        fragments = []
        pos, remaining, bar_index = start, duration, bi
        while remaining:
            length = min(remaining, times[bar_index + 1] - pos)
            if n is None and pos == times[bar_index] and length == times[bar_index + 1] - pos:
                pieces = [length]
            else:
                pieces = split_rhythm(pos - times[bar_index], length, n is None)
            for d in pieces:
                fragments.append((bar_index, pos, d))
                pos += d
            remaining -= length
            bar_index += 1
        for fi, (bar_index, pos, d) in enumerate(fragments):
            if n is None:
                if pos == times[bar_index] and d == times[bar_index + 1] - pos:
                    token = f'R1*{d / 4}'
                else:
                    token = 'r' + duration_token(d)
            else:
                names = [pitch(p)[0] for p in n['pitches']]
                token = (names[0] if len(names) == 1 else '<' + ' '.join(names) + '>') + duration_token(d)
                if fi < len(fragments) - 1:
                    token += '~'
                if with_decoration:
                    if fi == 0:
                        token += ''.join(ARTS[a] for a in n.get('articulations', []))
                        if n.get('hairpin_stop'):
                            token += '\\!'
                        if 'dynamic' in n:
                            token += '\\' + n['dynamic']
                        if 'text' in n:
                            token += '^\\markup \\italic ' + ly_string(n['text'])
                        if 'hairpin' in n:
                            token += '\\' + n['hairpin']
                        if n.get('slur_start'):
                            token += '('
                    if fi == len(fragments) - 1 and n.get('slur_end'):
                        token += ')'
                audit.append(dict(id=n['id'], bar=bar_index + 1, beat=str(pos),
                                  duration=str(d), pitches=[pitch(p)[1] for p in n['pitches']],
                                  tie_in=fi > 0, tie_out=fi < len(fragments) - 1))
            bar_tokens[bar_index].append(token)
    rows = []
    for i, tokens in enumerate(bar_tokens):
        rows.append(f'  % bar {i + 1}\n  ' + ' '.join(tokens) + f' | \\barNumberCheck #{i + 2}')
    rows.append('  \\bar "|."')
    return '\n'.join(rows), audit


def global_music(data, times, marks=False):
    rows = []
    for i, b in enumerate(data['bars']):
        cmds = []
        if marks:
            if 'rehearsal' in b:
                cmds.append('\\mark \\markup \\box ' + ly_string(b['rehearsal']))
        else:
            if 'meter' in b:
                cmds.append(f'\\time {b["meter"][0]}/{b["meter"][1]}')
            if 'key' in b:
                cmds.append(key_command(b['key']))
            if 'tempo' in b or 'text' in b:
                text = ly_string(b['text']) + ' ' if 'text' in b else ''
                number = f'4 = {b["tempo"]}' if 'tempo' in b else ''
                cmds.append('\\tempo ' + text + number)
        cmds.append('s1*' + str((times[i + 1] - times[i]) / 4))
        rows.append('  ' + ' '.join(cmds))
    return '\n'.join(rows)


def layout_music(part, times):
    rows = []
    for i in range(len(times) - 1):
        s = 's1*' + str((times[i + 1] - times[i]) / 4)
        if i + 1 in part.get('page_breaks', []):
            s += ' \\pageBreak'
        elif i + 1 in part.get('breaks', []):
            s += ' \\break'
        rows.append(s)
    return '\n'.join(rows)


def make_sources(data):
    if isinstance(data, dict) and data.get('schema_version') == 2:
        return make_sources_v2(data)
    times, counts = validate(data)
    common = ['\\version "2.24.3"', '\\language "nederlands"',
              'globalMusic = {', global_music(data, times), '}',
              'rehearsalMusic = {', global_music(data, times, True), '}']
    event_audit = {}
    for i, part in enumerate(data['parts']):
        music, audit = format_part(part, times)
        event_audit[part['id']] = audit
        common.extend([variable(i) + ' = \\absolute {', music, '}'])
    sources = {'music.ily': '\n'.join(common) + '\n'}
    header = '\\header {\n' + '\n'.join('  ' + k + ' = ' + ly_string(data[k])
                                        for k in ('title', 'subtitle', 'composer') if k in data) + '\n  tagline = ##f\n}\n'
    font = ly_string(data.get('font', 'serif'))
    for part_index in [None] + list(range(len(data['parts']))):
        is_score = part_index is None
        selected = list(range(len(data['parts']))) if is_score else [part_index]
        staff_size = 16 if is_score and len(selected) > 2 else 19
        preamble = '\\version "2.24.3"\n\\include "music.ily"\n' + header
        label = 'Full score' if is_score else data['parts'][part_index]['name']
        preamble += '\\header { instrument = ' + ly_string(label) + ' }\n'
        preamble += f'#(set-global-staff-size {staff_size})\n'
        preamble += '\\paper {\n  #(set-paper-size "a4")\n  top-margin = 12\\mm\n  bottom-margin = 12\\mm\n  left-margin = 15\\mm\n  right-margin = 12\\mm\n  print-page-number = ##t\n  print-first-page-number = ##f\n  ragged-last-bottom = ##t\n  ragged-bottom = ##f\n'
        preamble += '  #(define fonts (set-global-fonts #:roman ' + font + ' #:sans ' + font + '))\n}\n'
        music = []
        for j, i in enumerate(selected):
            p = data['parts'][i]
            music.append('\\new Staff \\with { instrumentName = ' + ly_string(p['name']) +
                         ' shortInstrumentName = ' + ly_string(p['short_name']) + ' } <<')
            music.append('  \\clef ' + ly_string(p['clef']) + ' \\numericTimeSignature \\globalMusic')
            if j == 0:
                music.append('  \\rehearsalMusic')
            if not is_score:
                music.append('  { ' + layout_music(p, times) + ' }')
            music.append('  \\new Voice { \\compressMMRests \\' + variable(i) + ' }\n>>')
        group = '\\new StaffGroup <<\n' if is_score else '<<\n'
        body = group + '\n'.join(music) + '\n>>'
        preamble += '\\score {\n' + body + '\n\\layout {\n  \\context { \\Score \\override BarNumber.break-visibility = ##(#f #f #t) }\n}\n}\n'
        name = 'score' if is_score else data['parts'][part_index]['id']
        sources[name + '.ly'] = preamble
    # Independent compiler readback of the emitted pitched rhythm. Decorations
    # are excluded so articulation playback cannot change the validation gate.
    audit_sources = ['\\version "2.24.3"', '\\language "nederlands"', '\\score { <<']
    for i, p in enumerate(data['parts']):
        bare, _ = format_part(p, times, False)
        audit_sources += ['\\new Staff \\with { instrumentName = ' + ly_string(p['id']) + ' } <<',
                          '{', global_music(data, times), '}', '\\absolute {', bare, '}', '>>']
    audit_sources += ['>> \\midi { } }']
    sources['audit.ly'] = '\n'.join(audit_sources) + '\n'
    # Fragment totals must exactly reconstruct each original event.
    for p in data['parts']:
        for n in p['notes']:
            a = [f for f in event_audit[p['id']] if f['id'] == n['id']]
            if not a or Fraction(a[0]['beat']) != rational(n['beat']) or sum(Fraction(f['duration']) for f in a) != rational(n['duration']):
                raise ValueError('Internal notation event reconstruction failure')
    return sources, dict(schema_version=1, bars=len(data['bars']), quarters=str(times[-1]),
                         parts=counts, fragments=event_audit, source_events_verified=True,
                         audio_verified=False, pdf_visually_reviewed=False)


def lane_commands(event, pedal=False):
    if pedal:
        return {'down': '\\sustainOn', 'up': '\\sustainOff',
                'change': '\\sustainOff\\sustainOn'}[event['action']]
    commands = '\\!' if event.get('hairpin_stop') else ''
    if 'dynamic' in event:
        commands += '\\' + event['dynamic']
    if 'hairpin' in event:
        commands += '\\' + event['hairpin']
    if 'text' in event:
        commands += '^\\markup \\italic ' + ly_string(event['text'])
    return commands


def format_lane(events, times, pedal=False, for_midi=False):
    """Position shared directions exactly, including release at the final barline."""
    at = {rational(e['beat']): lane_commands(e, pedal) for e in events}
    boundaries = sorted(set(times) | set(at))
    rows = []
    for start, end in zip(boundaries, boundaries[1:]):
        rows.append('s1*' + str((end - start) / 4) + at.get(start, ''))
    # A printed pedal bracket closes at the final barline automatically.
    # A zero-time release there can create a degenerate spanner in LilyPond.
    # Keep the explicit final release in the MIDI audit for exact CC64 timing.
    if times[-1] in at and (not pedal or for_midi):
        rows.append('<>' + at[times[-1]])
    return '\n'.join(rows)


def make_sources_v2(data):
    times, counts = validate(data)
    streams = list(notation_voices(data))
    common = ['\\version "2.24.3"', '\\language "nederlands"',
              'globalMusic = {', global_music(data, times), '}',
              'rehearsalMusic = {', global_music(data, times, True), '}']
    event_audit, variables = {}, {}
    for index, stream in enumerate(streams):
        music, audit = format_part(stream, times)
        variables[stream['id']] = variable(index)
        event_audit[stream['id']] = audit
        common.extend([variable(index) + ' = \\absolute {', music, '}'])
        # Check each original event in linear time, keeping identical notes in
        # different voices separate even if they share a pitch and an onset.
        reconstructed = {}
        for fragment in audit:
            state = reconstructed.setdefault(fragment['id'], [Fraction(fragment['beat']), Fraction(0)])
            state[1] += Fraction(fragment['duration'])
        for note in stream['notes']:
            if reconstructed.get(note['id']) != [rational(note['beat']), rational(note['duration'])]:
                raise ValueError('Internal notation event reconstruction failure')
    for index, part in enumerate(data['parts']):
        for kind in ('dynamics', 'pedal'):
            common.extend([kind + variable(index)[5:] + ' = {',
                           format_lane(part.get(kind, []), times, pedal=kind == 'pedal'), '}'])
    sources = {'music.ily': '\n'.join(common) + '\n'}
    for part_index in [None] + list(range(len(data['parts']))):
        is_score = part_index is None
        selected = list(range(len(data['parts']))) if is_score else [part_index]
        staff_count = sum(len(data['parts'][i]['staves']) for i in selected)
        staff_size = 16 if is_score and staff_count > 2 else 19
        label = 'Full score' if is_score else data['parts'][part_index]['name']
        header = '\\header {\n' + '\n'.join('  ' + k + ' = ' + ly_string(data[k])
                                            for k in ('title', 'subtitle', 'composer') if k in data)
        header += '\n  instrument = ' + ly_string(label) + '\n  tagline = ##f\n}\n'
        font = ly_string(data.get('font', 'serif'))
        preamble = '\\version "2.24.3"\n\\include "music.ily"\n' + header
        preamble += f'#(set-global-staff-size {staff_size})\n'
        preamble += '\\paper {\n  #(set-paper-size "a4")\n  top-margin = 12\\mm\n  bottom-margin = 12\\mm\n  left-margin = 15\\mm\n  right-margin = 12\\mm\n  print-page-number = ##t\n  print-first-page-number = ##f\n  ragged-last-bottom = ##t\n  ragged-bottom = ##f\n'
        preamble += '  #(define fonts (set-global-fonts #:roman ' + font + ' #:sans ' + font + '))\n}\n'
        blocks = []
        for position, index in enumerate(selected):
            part = data['parts'][index]
            piano = part.get('group') == 'piano'
            labels = 'instrumentName = ' + ly_string(part['name']) + ' shortInstrumentName = ' + ly_string(part['short_name'])
            if piano:
                blocks.append('\\new PianoStaff = ' + ly_string(part['id']) + ' \\with { ' + labels + ' } <<')
            for staff_index, staff in enumerate(part['staves']):
                staff_id = part['id'] + '/' + staff['id']
                settings = '' if piano else ' \\with { ' + labels + ' }'
                blocks.append('\\new Staff = ' + ly_string(staff_id) + settings + ' <<')
                blocks.append('  \\clef ' + ly_string(staff['clef']) + ' \\numericTimeSignature \\globalMusic')
                if position == 0 and staff_index == 0:
                    blocks.append('  \\rehearsalMusic')
                if not is_score and staff_index == 0:
                    blocks.append('  { ' + layout_music(part, times) + ' }')
                for voice_index, voice in enumerate(staff['voices']):
                    ident = staff_id + '/' + voice['id']
                    number = voice.get('voice_number', voice_index + 1)
                    style = '\\voice' + ('One', 'Two', 'Three', 'Four')[number - 1]
                    if len(staff['voices']) == 1 and 'voice_number' not in voice:
                        style = '\\oneVoice'
                    blocks.append('  \\new Voice = ' + ly_string(ident) + ' { ' + style +
                                  ' \\' + variables[ident] + ' }')
                blocks.append('>>')
                if staff_index == 0 and part.get('dynamics'):
                    blocks.append('\\new Dynamics = ' + ly_string(part['id'] + '-dynamics') +
                                  ' { \\dynamics' + variable(index)[5:] + ' }')
            if part.get('pedal'):
                blocks.append('\\new Dynamics = ' + ly_string(part['id'] + '-pedal') +
                              ' { \\set pedalSustainStyle = #\'mixed \\pedal' + variable(index)[5:] + ' }')
            if piano:
                blocks.append('>>')
        group = '\\new StaffGroup <<\n' if is_score and len(selected) > 1 else '<<\n'
        body = group + '\n'.join(blocks) + '\n>>'
        preamble += '\\score {\n' + body + '\n\\layout {\n  \\context { \\Score \\override BarNumber.break-visibility = ##(#f #f #t) }\n}\n}\n'
        name = 'score' if is_score else data['parts'][part_index]['id']
        sources[name + '.ly'] = preamble
    # One independent MIDI staff per logical voice prevents overlap/unison
    # merging from hiding a dropped event. Pedal control has its own audit staff.
    audit_sources = ['\\version "2.24.3"', '\\language "nederlands"', '\\score { <<']
    for stream in streams:
        bare, _ = format_part(stream, times, False)
        audit_sources += ['\\new Staff = ' + ly_string(stream['id']) + ' <<',
                          '{', global_music(data, times), '}', '\\absolute {', bare, '}', '>>']
    for part in data['parts']:
        if part.get('pedal'):
            audit_sources += ['\\new Staff = ' + ly_string('pedal/' + part['id']) + ' <<',
                              '{', global_music(data, times), '}',
                              '{', format_lane(part['pedal'], times, pedal=True, for_midi=True), '}', '>>']
    audit_sources += ['>> \\midi { } }']
    sources['audit.ly'] = '\n'.join(audit_sources) + '\n'
    return sources, dict(schema_version=2, bars=len(data['bars']), quarters=str(times[-1]),
                         parts=counts, fragments=event_audit, source_events_verified=True,
                         voices=[{k: v for k, v in s.items() if k != 'notes'} for s in streams],
                         audio_verified=False, pdf_visually_reviewed=False)


def export(data, out_dir, lilypond=None):
    """Publish a fresh directory after all requested compilations succeed."""
    out = Path(out_dir).resolve()
    if out.exists():
        raise FileExistsError(out)
    sources, report = make_sources(data)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Windows LilyPond/Guile builds may fail before parsing when their working
    # directory includes non-ASCII characters. Compile in the OS temp directory.
    with tempfile.TemporaryDirectory(prefix='engraving-') as tmp:
        stage = Path(tmp) / 'result'
        stage.mkdir()
        for name, content in sources.items():
            (stage / name).write_text(content, encoding='utf-8')
        (stage / 'notation.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        if lilypond:
            executable = str(Path(shutil.which(str(lilypond)) or lilypond).resolve(strict=True))
            env = {**os.environ, 'LC_ALL': 'C', 'LANG': 'C'}
            version = subprocess.run([executable, '--version'], capture_output=True, timeout=30, env=env)
            if version.returncode:
                raise RuntimeError('LilyPond version check failed')
            report['lilypond_version'] = version.stdout.decode('utf-8', errors='replace').splitlines()[0]
            for name in sources:
                if not name.endswith('.ly'):
                    continue
                done = subprocess.run([executable, '-dno-point-and-click', '-o', Path(name).stem, name],
                                      cwd=stage, capture_output=True, timeout=180, env=env)
                log = (done.stdout + done.stderr).decode('utf-8', errors='replace')
                (stage / (Path(name).stem + '.log')).write_text(log, encoding='utf-8')
                warning = re.search(r'warning:|error:|fatal error:|programming error:', log, re.I)
                if done.returncode or warning:
                    raise RuntimeError(f'LilyPond {name} exited {done.returncode} or needs review:\n{log[-6000:]}')
                suffix = '.midi' if name == 'audit.ly' else '.pdf'
                target = stage / (Path(name).stem + suffix)
                if suffix == '.midi' and not target.exists() and target.with_suffix('.mid').exists():
                    target.with_suffix('.mid').rename(target)
                magic = b'MThd' if suffix == '.midi' else b'%PDF-'
                if not target.is_file() or not target.read_bytes().startswith(magic):
                    raise RuntimeError(f'Missing or invalid {target.name}')
            report['compiled_without_warnings'] = True
        report['files_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in stage.iterdir() if p.is_file()}
        (stage / 'engraving-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        # Keep final publication on the output volume even when compilation
        # happened on another drive.
        with tempfile.TemporaryDirectory(prefix='.engraving-', dir=out.parent) as publication:
            ready = Path(publication) / 'result'
            shutil.copytree(stage, ready)
            ready.rename(out)
    return {k: v for k, v in report.items() if k not in ('fragments', 'files_sha256')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('notation')
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--lilypond', help='Path or command; omit to generate source only')
    args = parser.parse_args()
    print(json.dumps(export(load_json(args.notation), args.out_dir, args.lilypond), ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise SystemExit(str(exc))

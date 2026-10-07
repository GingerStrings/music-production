"""Musically neutral event validation and timing conversion; Python 3.10+."""
import json
import math
from pathlib import Path
from music_timeline import TempoMap, validate_meters

MAX_EVENTS = 200_000


def finite(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f"{label} outside supported range")
    return value


def integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return value


def reject_keys(obj, allowed, label):
    if not isinstance(obj, dict):
        raise ValueError(f"{label} must be an object")
    extra = set(obj) - set(allowed.split())
    if extra:
        raise ValueError(f"Unknown {label} fields: {', '.join(sorted(extra))}")


def load_json(path):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError(f"Duplicate JSON key: {k}")
            result[k] = v
        return result
    p = Path(path)
    if p.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("JSON input exceeds 64 MiB")
    return json.loads(p.read_text(encoding='utf-8-sig'), object_pairs_hook=unique)


def new_file(path, data):
    """Create one new output; never overwrite an existing file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as handle:
        handle.write(data)


def save_json(path, value):
    new_file(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))


def event_key(event):
    # Controller setup precedes simultaneous note-ons. Stable order is retained
    # among same-time controllers (command sequences may depend on that order).
    return event['beat'], 0 if event['type'] == 'cc' else 1


def validate_performance(data):
    v2 = data.get('schema_version') == 2
    reject_keys(data, 'schema_version kind title end_beats tracks timing_report ' +
                ('tempo_map meter_map source_report' if v2 else 'bpm meter'), 'performance')
    if type(data['schema_version']) is not int or data['schema_version'] not in (1,2) or data['kind'] != 'performance':
        raise ValueError("Expected performance schema version 1 or 2")
    if v2:
        TempoMap(data['tempo_map'])
        validate_meters(data['meter_map'])
    else:
        finite(data['bpm'], 'bpm', 1, 1000)
        meter = data['meter']
        if not isinstance(meter, list) or len(meter) != 2:
            raise ValueError("meter must be [numerator, denominator]")
        validate_meters([dict(beat=0, numerator=meter[0], denominator=meter[1])])
    end = finite(data['end_beats'], 'end_beats', 0.000001, 10_000_000)
    if v2 and any(p['beat'] > end for key in ('tempo_map', 'meter_map') for p in data[key]):
        raise ValueError('Timeline point extends past end_beats')
    if not isinstance(data['tracks'], list) or not 1 <= len(data['tracks']) <= 128:
        raise ValueError("Expected 1..128 tracks")
    seen, total = set(), 0
    for track in data['tracks']:
        reject_keys(track, 'template_index events' + (' name source_tracks' if v2 else ''), 'performance track')
        if 'name' in track and (not isinstance(track['name'],str) or not track['name'].strip() or '\0' in track['name']):
            raise ValueError('Invalid track name')
        index = integer(track['template_index'], 'template_index', 1, 128)
        if index in seen:
            raise ValueError("Duplicate template track index")
        seen.add(index)
        if not isinstance(track['events'], list):
            raise ValueError("events must be an array")
        total += len(track['events'])
        if total > MAX_EVENTS:
            raise ValueError("Excessive event count")
        previous = -1.0
        for e in track['events']:
            reject_keys(e, 'type beat channel pitch velocity duration controller value program release_velocity', 'event')
            t = finite(e['beat'], 'event beat', 0, end)
            if t < previous:
                raise ValueError("Events must be sorted in time")
            previous = t
            integer(e['channel'], 'channel', 0, 15)
            if e['type'] == 'note':
                if set(e) - ({'release_velocity'} if v2 else set()) != {'type', 'beat', 'channel', 'pitch', 'velocity', 'duration'}:
                    raise ValueError("Invalid note fields")
                integer(e['pitch'], 'pitch', 0, 127)
                integer(e['velocity'], 'velocity', 1, 127)
                if 'release_velocity' in e:integer(e['release_velocity'],'release_velocity',0,127)
                duration = finite(e['duration'], 'duration', 0 if v2 else 1e-8)
                if t + duration > end + 1e-8:
                    raise ValueError("Note extends past end_beats")
            elif e['type'] == 'cc':
                if set(e) != {'type', 'beat', 'channel', 'controller', 'value'}:
                    raise ValueError("Invalid CC fields")
                integer(e['controller'], 'controller', 0, 127)
                integer(e['value'], 'CC value', 0, 127)
            elif v2 and e['type'] in ('pitchbend','program'):
                key = 'value' if e['type']=='pitchbend' else 'program'
                if set(e) != {'type','beat','channel',key}:
                    raise ValueError('Invalid extended MIDI fields')
                integer(e[key], key, -8192 if key=='value' else 0, 8191 if key=='value' else 127)
            else:
                raise ValueError("Unsupported MIDI event type for this schema")
    return data


def compile_score(score):
    """Convert explicitly supplied decisions; never invent music or mappings."""
    v2=score.get('schema_version')==2
    reject_keys(score, 'schema_version kind title preroll_beats end_beats tracks '+
                ('tempo_map meter_map' if v2 else 'bpm meter'), 'score')
    if type(score['schema_version']) is not int or score['schema_version'] not in (1,2) or score['kind'] != 'score':
        raise ValueError("Expected score schema version 1 or 2")
    bpm = score['tempo_map'][0]['bpm'] if v2 else finite(score['bpm'], 'bpm', 1, 1000)
    pre = finite(score['preroll_beats'], 'preroll_beats', 0)
    timeline=TempoMap(score['tempo_map'] if v2 else [dict(beat=0,bpm=bpm,curve='step')])
    result = {k: score[k] for k in ('schema_version', 'title', 'end_beats')+
              (('tempo_map','meter_map') if v2 else ('bpm','meter'))}
    result.update(kind='performance', tracks=[])
    report = {'documented': 0, 'measured': 0, 'estimated': 0, 'none': 0}
    if not isinstance(score['tracks'], list) or not 1 <= len(score['tracks']) <= 128:
        raise ValueError("Expected 1..128 tracks")
    total = 0
    for track in score['tracks']:
        reject_keys(track, 'template_index notes controllers', 'score track')
        events = []
        for n in track['notes']:
            reject_keys(n, 'beat duration pitch velocity channel advance_ms release_advance_ms timing_basis evidence', 'score note')
            beat = finite(n['beat'], 'score beat', 0)
            duration = finite(n['duration'], 'score duration', 1e-8)
            advance = finite(n['advance_ms'], 'advance_ms', 0, 10000)
            release = finite(n.get('release_advance_ms', advance), 'release_advance_ms', -10000, 10000)
            basis = n['timing_basis']
            if basis not in report or basis == 'none' and (advance != 0 or release != 0):
                raise ValueError("Invalid timing_basis")
            evidence = n.get('evidence')
            if basis in ('documented', 'measured') and (not isinstance(evidence, str) or not evidence.strip()):
                raise ValueError("Documented/measured timing requires evidence")
            report[basis] += 1
            start = timeline.advance(pre+beat,advance)
            end = timeline.advance(pre+beat+duration,release)
            events.append(dict(type='note', beat=start, duration=end-start,
                               pitch=n['pitch'], velocity=n['velocity'], channel=n.get('channel', 0)))
        for c in track['controllers']:
            reject_keys(c, 'beat controller value channel advance_ms', 'score controller')
            # CC may be pre-positioned in preroll using a negative score beat.
            beat = finite(c['beat'], 'CC score beat')
            advance = finite(c['advance_ms'], 'CC advance_ms', 0, 10000)
            events.append(dict(type='cc', beat=timeline.advance(pre+beat,advance),
                               controller=c['controller'], value=c['value'], channel=c.get('channel', 0)))
        total += len(events)
        if total > MAX_EVENTS:
            raise ValueError("Excessive event count")
        events.sort(key=event_key)
        result['tracks'].append(dict(template_index=track['template_index'], events=events))
    result['timing_report'] = dict(note_timing_basis=report, latency_measured_by_this_tool=False,
                                   note='Evidence is caller supplied; this tool only converts time coordinates.')
    return validate_performance(result)

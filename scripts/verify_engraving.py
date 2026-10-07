"""Read LilyPond MIDI and PDF artifacts back; requires mido and pypdf.

This verifies event preservation and PDF presence, not musical judgment,
page appearance, playing technique, plugin loading or rendered audio.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from engrave import make_sources, notation_voices, pitch, rational
from music_data import load_json, save_json


def read_track(track, ppq):
    active, result, tick = {}, [], 0
    for msg in track:
        tick += msg.time
        if msg.type == 'note_on' and msg.velocity > 0:
            key = msg.channel, msg.note
            if key in active:
                raise ValueError('Duplicate simultaneous MIDI note-on')
            active[key] = tick
        elif msg.type == 'note_off' or msg.type == 'note_on' and msg.velocity == 0:
            key = msg.channel, msg.note
            if key not in active:
                raise ValueError('MIDI note-off without note-on')
            start = active.pop(key)
            if tick <= start:
                raise ValueError('Non-positive MIDI note duration')
            result.append((Fraction(start, ppq), msg.note, Fraction(tick - start, ppq)))
    if active:
        raise ValueError('Unclosed MIDI note')
    return sorted(result)


def read_pedal(track, ppq):
    tick, result = 0, []
    for msg in track:
        tick += msg.time
        if msg.type == 'control_change' and msg.control == 64:
            result.append((Fraction(tick, ppq), msg.value))
    return result


def named_payloads(midi, reader):
    result = {}
    for track in midi.tracks:
        payload = reader(track, midi.ticks_per_beat)
        if not payload:
            continue
        names = [m.name for m in track if m.type == 'track_name']
        if len(names) != 1:
            raise ValueError('Expected one LilyPond audit track identity')
        # Named Staff contexts are written as "context-id:" by LilyPond.
        ident = names[0].removesuffix(':')
        if ident in result:
            raise ValueError('Duplicate LilyPond audit track identity')
        result[ident] = payload
    return result


def verify(folder):
    import mido
    from pypdf import PdfReader
    root = Path(folder)
    data = load_json(root/'notation.json')
    recorded = load_json(root/'engraving-report.json')
    if not recorded.get('compiled_without_warnings'):
        raise ValueError('Engraving has not been successfully compiled')
    for name, expected in recorded['files_sha256'].items():
        if Path(name).name != name or hashlib.sha256((root/name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Artifact fingerprint mismatch: {name}')
    sources, _ = make_sources(data)
    for name, content in sources.items():
        if (root/name).read_text(encoding='utf-8') != content:
            raise ValueError(f'Generated source differs from notation: {name}')
    midi = mido.MidiFile(root/'audit.midi')
    tracks = [read_track(t, midi.ticks_per_beat) for t in midi.tracks]
    tracks = [t for t in tracks if t]
    parts = [p for p in notation_voices(data) if p['notes']]
    if len(tracks) != len(parts):
        raise ValueError('MIDI logical voice count mismatch')
    if data['schema_version'] == 2:
        by_id = named_payloads(midi, read_track)
        if set(by_id) != {p['id'] for p in parts}:
            raise ValueError('MIDI logical voice identities mismatch')
        tracks = [by_id[p['id']] for p in parts]
    reports = []
    for part, actual in zip(parts, tracks):
        expected = sorted((rational(n['beat']), pitch(p)[1], rational(n['duration']))
                          for n in part['notes'] for p in n['pitches'])
        if actual != expected:
            mismatch = next(((a,e) for a,e in zip(actual, expected) if a != e), None)
            raise ValueError(f'MIDI event mismatch in {part["id"]}: actual {len(actual)}, expected {len(expected)}, {mismatch}')
        reports.append(dict(id=part['id'], pitches=len(actual), exact_onsets_pitches_durations=True))
    pedal_report = []
    if data['schema_version'] == 2:
        pedal_parts = [p for p in data['parts'] if p.get('pedal')]
        by_id = named_payloads(midi, read_pedal)
        if set(by_id) != {'pedal/' + p['id'] for p in pedal_parts}:
            raise ValueError('MIDI sustain pedal track identities mismatch')
        pedal_tracks = [by_id['pedal/' + p['id']] for p in pedal_parts]
        for part, actual in zip(pedal_parts, pedal_tracks):
            expected = []
            for event in part['pedal']:
                values = {'down': [127], 'up': [0], 'change': [0, 127]}[event['action']]
                expected.extend((rational(event['beat']), value) for value in values)
            if actual != expected:
                raise ValueError(f'MIDI sustain pedal mismatch in {part["id"]}: {actual} != {expected}')
            pedal_report.append(dict(id=part['id'], events=len(actual), exact_beats_and_states=True))
    pdfs = []
    for name in ['score'] + [p['id'] for p in data['parts']]:
        path = root/(name+'.pdf')
        pdf = PdfReader(path)
        if not pdf.pages:
            raise ValueError('Empty PDF')
        for page in pdf.pages:
            if float(page.mediabox.width) < 100 or float(page.mediabox.height) < 100:
                raise ValueError('Invalid PDF page dimensions')
        pdfs.append(dict(file=path.name, pages=len(pdf.pages), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    result = dict(schema_version=data['schema_version'], lilypond_version=recorded['lilypond_version'],
                artifact_hashes_match=True, generated_sources_match_notation=True,
                midi_parts=reports, pdfs=pdfs, pdf_visually_reviewed=False,
                original_transcription_accuracy_assessed=False, audio_verified=False)
    if data['schema_version'] == 2:
        result['midi_pedals'] = pedal_report
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder'); p.add_argument('--report', required=True)
    args = p.parse_args()
    report = verify(args.folder)
    save_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

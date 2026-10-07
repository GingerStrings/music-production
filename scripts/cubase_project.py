#!/usr/bin/env python3
"""Static Cubase template adapter. No DAW, plugin, UI, network or MCP required."""
import argparse
import hashlib
import math
from pathlib import Path
import struct
import sys

from cpr_archive import Archive, Node, riff_chunks
from cpr_fields import read_attrs, encode_attrs, text_value, walk
from cpr_midi import parse_midi, encode_event, compare_events, PPQ
from cpr_timeline import read_tempo, read_meter, write_tempo, write_meter
from music_timeline import TempoMap
from music_data import load_json, save_json, new_file, compile_score, validate_performance

ADAPTER = 'observed-rif2-existing-instruments-v3'
LIMIT = 128 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def exactly(nodes, name):
    found = [n for n in nodes if n.name == name]
    if len(found) != 1:
        raise ValueError(f"Expected one {name}, found {len(found)}")
    return found[0]


def root_archives(data, chunks):
    result = {}
    for i, (tag, _, start, end) in enumerate(chunks):
        if tag != b'ROOT':
            continue
        if end-start < 4:
            raise ValueError('Truncated ROOT name')
        size = struct.unpack_from('>I', data, start)[0]
        if not 0 < size <= end-start-4:
            raise ValueError('Invalid ROOT name')
        name = data[start+4:start+4+size].rstrip(b'\0').decode('utf-8')
        if name in result or i+1 >= len(chunks) or chunks[i+1][0] != b'ARCH':
            raise ValueError('Unsupported ROOT/ARCH pairing')
        result[name] = i+1
    return result


def read_archive(data, chunks, index):
    _, _, start, end = chunks[index]
    archive = Archive(data, start, end)
    if archive.serialize(True) != data[start:end]:
        raise ValueError('Archive failed byte-identical round trip')
    return archive


class Project:
    def __init__(self, data):
        if len(data) > LIMIT:
            raise ValueError('CPR exceeds this adapter\'s 128 MiB limit')
        self.data, self.chunks = data, riff_chunks(data)
        roots = root_archives(data, self.chunks)
        if 'Arrangement1' not in roots or 'Devices' not in roots:
            raise ValueError('This adapter requires Arrangement1 and Devices archives')
        self.main_index, self.device_index = roots['Arrangement1'], roots['Devices']
        self.archive = read_archive(data, self.chunks, self.main_index)
        self.devices = read_archive(data, self.chunks, self.device_index)
        nodes = list(self.archive.root.walk())
        self.tempo = exactly(nodes, 'MTempoTrackEvent')
        self.signature = exactly(nodes, 'MSignatureTrackEvent')
        self.tempo_map,_,self.tempo_mode=read_tempo(data,self.tempo)
        self.meter_map,*_=read_meter(data,self.signature)
        self.bpm=self.tempo_mode['fallback_bpm'] if self.tempo_mode['fixed_tempo'] else self.tempo_map[0]['bpm']
        self.meter=[self.meter_map[0]['numerator'],self.meter_map[0]['denominator']]
        self.tracks = [n for n in nodes if n.name == 'MInstrumentTrackEvent']
        if not 1 <= len(self.tracks) <= 128:
            raise ValueError('Expected 1..128 existing instrument tracks')
        if any(n.name in ('MAudioTrackEvent', 'MMidiTrackEvent', 'MAudioPart', 'MWaveEvent') for n in nodes):
            raise ValueError('Additional audio/MIDI track types require another adapter')
        if sum(n.name == 'MMidiPart' for n in nodes) != len(self.tracks):
            raise ValueError('Requires exactly one MIDI part per instrument track')
        self.info, self.parts, self.events = [], [], []
        for index, track in enumerate(self.tracks, 1):
            part_event = exactly(track.walk(), 'MMidiPartEvent')
            part = exactly(track.walk(), 'MMidiPart')
            instrument = exactly(track.walk(), 'MInstrumentTrack')
            for placement in (part_event, track):
                if placement.data_start+18 > placement.end:
                    raise ValueError('Truncated event placement')
                start, duration = struct.unpack_from('>dd', data, placement.data_start+2)
                if start != 0 or not math.isfinite(duration) or duration <= 0:
                    raise ValueError('Requires zero-position instrument tracks and MIDI parts')
            part_length = struct.unpack_from('>d', data, part_event.data_start+10)[0] / PPQ
            # Relative prefix length observed in the supported saved template family.
            # A round trip and required attribute paths guard this local assumption.
            attrs_start = instrument.data_start+29
            attrs, attrs_end = read_attrs(data, attrs_start, instrument.end)
            if encode_attrs(attrs) != data[attrs_start:attrs_end]:
                raise ValueError('Instrument attributes failed round trip')
            fields = dict(walk(attrs))
            for required in [('Name', 'String'), ('Synth Slot', 'Plugin', 'audioComponent'),
                             ('Synth Slot', 'Plugin', 'Plugin UID', 'GUID')]:
                if required not in fields:
                    raise ValueError(f'Missing instrument attribute: {required}')
            # Existing host automation could override newly authored CC expression.
            # The adapter preserves it and reports it; the build rejects nonempty lanes.
            auto_points = 0
            for n in track.walk():
                if n.name == 'MAutoListNode':
                    if n.end-n.data_start < 28:
                        raise ValueError('Unsupported automation list')
                    auto_points += struct.unpack_from('>I', data, n.data_start+24)[0]
            cc_offset, event_start, events = parse_midi(data, part)
            state = fields[('Synth Slot', 'Plugin', 'audioComponent')].value
            controller = fields.get(('Synth Slot', 'Plugin', 'editController'))
            insert = fields.get(('Midi Channel', 'MidiInsertFolder', 'Bypass Inserts'))
            self.info.append(dict(index=index, name=text_value(fields[('Name', 'String')]),
                                  plugin_uid=text_value(fields[('Synth Slot', 'Plugin', 'Plugin UID', 'GUID')]),
                                  component_sha256=digest(state),
                                  controller_sha256=digest(controller.value) if controller is not None else None,
                                  instrument_sha256=digest(data[instrument.data_start:instrument.end]),
                                  part_beats=part_length, events=len(events),
                                  host_automation_points=auto_points,
                                  midi_inserts_bypassed=insert.value if insert is not None else None))
            self.parts.append((track, part_event, part, cc_offset, event_start))
            self.events.append(events)
        self.transport = exactly(self.devices.root.walk(), 'FAttributes')
        attrs, end = read_attrs(data, self.transport.data_start, self.transport.end)
        if end != self.transport.end or encode_attrs(attrs) != data[self.transport.data_start:end]:
            raise ValueError('Transport attributes failed round trip')
        self.transport_attrs = attrs
        self.transport_fields = dict(walk(attrs))
        for name in ('Time', 'Time2', 'Cycle Left', 'Cycle Right', 'Punch Left', 'Punch Right'):
            field = self.transport_fields.get(('Transport', name, 'Time'))
            domain = self.transport_fields.get(('Transport', name, 'Domain', 'Type'))
            period = self.transport_fields.get(('Transport', name, 'Domain', 'Period'))
            if field is None or field.typ != 4 or domain is None or domain.value != 1 or period is None or period.value != 1:
                raise ValueError('Requires the observed seconds-based transport domain')

    def profile(self):
        class_count = self.archive.validate_class_registry()
        return dict(schema_version=1, adapter=ADAPTER, template_sha256=digest(self.data),
                    archive_class_count=class_count,
                    template_bytes=len(self.data), bpm=self.bpm, meter=self.meter, tracks=self.info,
                    tempo_map=self.tempo_map,meter_map=self.meter_map,tempo_mode=self.tempo_mode,
                    static_roundtrip=True, runtime_tested=False,
                    boundary='Existing instrument tracks, one MIDI part each; timeline and MIDI edits; no plugin state edits.')

    def build(self, performance):
        self.archive.validate_class_registry()
        p = validate_performance(performance)
        v2=p['schema_version']==2
        if not v2 and (len(self.tempo_map)!=1 or len(self.meter_map)!=1 or not math.isclose(p['bpm'], self.bpm, abs_tol=0.0001, rel_tol=0) or p['meter'] != self.meter):
            raise ValueError('Tempo/meter differs from template. Extend and verify an adapter or supply a matching template; do not silently change the music.')
        if v2:
            timeline=write_tempo(self.data,self.tempo,p['tempo_map'])
            write_meter(self.data,self.signature,p['meter_map'])
        else:timeline=TempoMap([dict(beat=0,bpm=p['bpm'],curve='step')])
        by_index = {t['template_index']: t for t in p['tracks']}
        if set(by_index) != set(range(1, len(self.tracks)+1)):
            raise ValueError('Supply every template instrument track exactly once; use an empty events list for silence')
        for info in self.info:
            if info['host_automation_points']:
                raise ValueError('Nonempty host automation needs an explicit conflict policy and another adapter')
            if info['midi_inserts_bypassed'] != 1:
                raise ValueError('Template MIDI inserts are not confirmed bypassed; inspect their effect before using this adapter')
        for index, (track, placement, part, count_offset, event_start) in enumerate(self.parts, 1):
            events = by_index[index]['events']
            prefix=b'\0' if count_offset+4==part.end else b''
            part.raw_replace(event_start, part.end, prefix+b''.join(encode_event(e) for e in events))
            part.raw_replace(count_offset, count_offset+4, struct.pack('>I', len(events)))
            for target in (track, placement):
                target.raw_replace(target.data_start+10, target.data_start+18,
                                   struct.pack('>d', p['end_beats']*PPQ))
        main = self.archive.serialize(True)
        # Fixed-size scalar patches preserve all unknown transport fields and refs.
        seconds = timeline.beat_to_seconds(p['end_beats'])
        for name, value in [('Time', 0.), ('Time2', 0.), ('Cycle Left', 0.),
                            ('Cycle Right', seconds), ('Punch Left', 0.), ('Punch Right', seconds)]:
            self.transport_fields[('Transport', name, 'Time')].value = value
        encoded = encode_attrs(self.transport_attrs)
        if len(encoded) != self.transport.end-self.transport.data_start:
            raise ValueError('Unexpected transport size change')
        # Do not relocate an opaque FAttributes payload after replacing it: the
        # unchanged archive size lets this exact offset patch preserve all refs.
        devices = bytearray(self.data[self.devices.start:self.devices.end])
        offset = self.transport.data_start-self.devices.start
        devices[offset:offset+len(encoded)] = encoded
        body = bytearray()
        for i, (tag, _, start, end) in enumerate(self.chunks):
            payload = main if i == self.main_index else bytes(devices) if i == self.device_index else self.data[start:end]
            body.extend(tag + struct.pack('>Q', len(payload)) + payload)
        output = b'RIF2' + struct.pack('>Q', len(body)) + b'NUND' + body
        check = Project(output)
        check.archive.validate_class_registry()
        for index, (before, after) in enumerate(zip(self.info, check.info), 1):
            if before['instrument_sha256'] != after['instrument_sha256']:
                raise ValueError('Opaque instrument state or routing changed during relocation')
            if not math.isclose(after['part_beats'], p['end_beats'], abs_tol=1e-8, rel_tol=0):
                raise ValueError('MIDI part extent differs after writing')
            compare_events(check.events[index-1], by_index[index]['events'])
        expected_tempos=p['tempo_map'] if v2 else self.tempo_map
        expected_meters=p['meter_map'] if v2 else self.meter_map
        if check.meter_map!=expected_meters or len(check.tempo_map)!=len(expected_tempos):
            raise ValueError('Tempo/meter map length or signature readback mismatch')
        for actual,expected in zip(check.tempo_map,expected_tempos):
            if actual['beat']!=expected['beat'] or actual['curve']!=expected['curve'] or not math.isclose(actual['bpm'],expected['bpm'],rel_tol=1e-7):
                raise ValueError('Tempo readback mismatch')
        if v2 and check.tempo_mode['fixed_tempo']:raise ValueError('Tempo track was not enabled')
        for name, expected in [('Time', 0.), ('Time2', 0.), ('Cycle Left', 0.),
                               ('Cycle Right', seconds), ('Punch Left', 0.), ('Punch Right', seconds)]:
            actual = check.transport_fields[('Transport', name, 'Time')].value
            if not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-8):
                raise ValueError('Transport readback mismatch')
        report = dict(schema_version=1, adapter=ADAPTER, static_validation_passed=True,
                      output_sha256=digest(output), source_sha256=digest(self.data),
                      instrument_tracks=len(self.tracks),
                      notes=sum(e['type']=='note' for t in p['tracks'] for e in t['events']),
                      controllers=sum(e['type']=='cc' for t in p['tracks'] for e in t['events']),
                      pitch_bends=sum(e['type']=='pitchbend' for t in p['tracks'] for e in t['events']),
                      program_changes=sum(e['type']=='program' for t in p['tracks'] for e in t['events']),
                      tempo_map=check.tempo_map,meter_map=check.meter_map,
                      bpm=check.bpm, meter=check.meter, end_beats=p['end_beats'], seconds=seconds,
                      instrument_state_and_routing_unchanged=True, plugin_executed=False, runtime_tested=False,
                      timing_report=p.get('timing_report'),
                      checks=['Archive bounds and round trip', 'Every note and CC read back',
                              'Opaque instrument/routing hashes preserved', 'Part extents and locators'],
                      limitations=['Cubase loading, plugin loading and audio output have not been tested.',
                                   'This adapter preserves existing track names, mixer settings, markers and project metadata.',
                                   'Timing values are caller supplied and were not measured by this script.'])
        return output, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect', help='Read a compatible CPR and record its fingerprint')
    inspect.add_argument('template')
    inspect.add_argument('--out', required=True)
    compile_cmd = commands.add_parser('compile', help='Convert explicit score timing to performance events')
    compile_cmd.add_argument('score')
    compile_cmd.add_argument('--out', required=True)
    build = commands.add_parser('build', help='Replace existing instrument MIDI in a new CPR')
    build.add_argument('template')
    build.add_argument('--profile', required=True)
    build.add_argument('--performance', required=True)
    build.add_argument('--out', required=True)
    build.add_argument('--report', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'compile':
            result = compile_score(load_json(args.score))
            save_json(args.out, result)
            print('Performance written; timing estimates remain estimates.')
            return 0
        template = Path(args.template)
        if template.suffix.lower() != '.cpr' or template.stat().st_size > LIMIT:
            raise ValueError('Expected a .cpr file up to 128 MiB')
        source = template.read_bytes()
        project = Project(source)
        if args.command == 'inspect':
            save_json(args.out, project.profile())
            print(f'Inspected {len(project.tracks)} instrument tracks; static round trip passed.')
            return 0
        profile = load_json(args.profile)
        if profile.get('adapter') != ADAPTER or profile.get('template_sha256') != digest(source):
            raise ValueError('Template fingerprint differs from the inspected profile')
        out, report_path = Path(args.out), Path(args.report)
        inputs = {p.resolve() for p in (template, Path(args.profile), Path(args.performance))}
        if out.suffix.lower() != '.cpr' or out.exists() or report_path.exists():
            raise ValueError('Choose new output CPR and report filenames')
        if out.resolve() in inputs or report_path.resolve() in inputs or out.resolve() == report_path.resolve():
            raise ValueError('Input and output paths must be distinct')
        output, report = project.build(load_json(args.performance))
        if template.read_bytes() != source:
            raise ValueError('Source template changed during processing')
        # All semantic checks run in memory before the exclusive output creation.
        new_file(out, output)
        if out.read_bytes() != output:
            raise ValueError('Output bytes differ after disk write')
        save_json(report_path, report)
        print(f'CPR written and statically verified: {report["notes"]} notes, {report["controllers"]} CC events.')
        return 0
    except (ValueError, KeyError, TypeError, IndexError, StopIteration, struct.error, OSError, RecursionError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())

"""Synthetic behavioral tests; no vendor files, plugins or DAW required."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cpr_archive import Archive, Node, Raw, riff_chunks
from cpr_fields import Field, encode_attrs, read_attrs, text_value
from cpr_midi import encode_event, parse_midi, compare_events
from music_data import compile_score, validate_performance, load_json, new_file


def full(name, payload, version=0):
    label = name.encode('ascii') + b'\0'
    return b'\xff'*8 + struct.pack('>I', len(label)) + label + struct.pack('>HQ', version, len(payload)) + payload


def midi_part(records, count):
    payload = struct.pack('>I', 5) + b'demo\0' + b'\0'*20 + struct.pack('>IB', count, 0) + records
    return full('MMidiPart', payload)


def example():
    return load_json(ROOT / 'examples/score.json')


class TimingTests(unittest.TestCase):
    def test_note_and_cc_use_independent_timing(self):
        score = example()
        data = compile_score(score)
        events = data['tracks'][0]['events']
        first_note = next(e for e in events if e['type'] == 'note')
        self.assertAlmostEqual(first_note['beat'], 1.84)
        self.assertAlmostEqual(first_note['duration'], 1)
        self.assertEqual(events[0]['beat'], 1)
        self.assertFalse(data['timing_report']['latency_measured_by_this_tool'])
        self.assertEqual(score['tracks'][0]['notes'][0]['beat'], 0)

    def test_release_can_be_independent_from_attack(self):
        score = example()
        score['tracks'][0]['notes'][0]['release_advance_ms'] = 20
        n = next(e for e in compile_score(score)['tracks'][0]['events'] if e['type']=='note')
        self.assertAlmostEqual(n['beat'] + n['duration'], 2.96)

    def test_insufficient_preroll_is_rejected_not_clamped(self):
        score = example()
        score['preroll_beats'] = 0
        with self.assertRaises(ValueError):
            compile_score(score)

    def test_unknown_timing_fields_are_not_ignored(self):
        score = example()
        score['tracks'][0]['notes'][0]['latency_ms'] = 80
        with self.assertRaises(ValueError):
            compile_score(score)

    def test_measured_label_requires_evidence(self):
        score = example()
        score['tracks'][0]['notes'][0]['timing_basis'] = 'measured'
        for invalid in [None, '', 123, False]:
            with self.subTest(evidence=invalid):
                score['tracks'][0]['notes'][0]['evidence'] = invalid
                with self.assertRaises(ValueError):
                    compile_score(score)

    def test_same_time_commands_keep_their_order_before_note(self):
        score = example()
        score['tracks'][0]['notes'] = [dict(beat=0, duration=1, pitch=60, velocity=80,
                                                  advance_ms=0, timing_basis='none')]
        score['tracks'][0]['controllers'] = [dict(beat=0, controller=58, value=v, advance_ms=0) for v in (3, 78)]
        events = compile_score(score)['tracks'][0]['events']
        self.assertEqual([e.get('value') for e in events], [3, 78, None])

    def test_invalid_event_data(self):
        for field, value in [('pitch', 128), ('velocity', 0), ('channel', 16),
                             ('beat', float('nan')), ('duration', -1), ('pitch', True)]:
            with self.subTest(field=field, value=value):
                p = compile_score(example())
                event = next(e for e in p['tracks'][0]['events'] if e['type']=='note')
                event[field] = value
                with self.assertRaises(ValueError):
                    validate_performance(p)

    def test_duplicate_json_and_overwrite_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'data.json'
            new_file(path, b'{"a":1,"a":2}')
            with self.assertRaises(ValueError):
                load_json(path)
            with self.assertRaises(FileExistsError):
                new_file(path, b'changed')
            self.assertEqual(path.read_bytes(), b'{"a":1,"a":2}')


class MidiTests(unittest.TestCase):
    def test_native_roundtrip_and_independent_numeric_fields(self):
        events = compile_score(example())['tracks'][0]['events']
        records = b''.join(encode_event(e) for e in events)
        raw = midi_part(records, len(events))
        archive = Archive(raw, 0, len(raw))
        node = archive.root.get('MMidiPart')
        _, event_start, actual = parse_midi(raw, node)
        compare_events(actual, events)
        # Independent check of the first fixed record, outside the roundtrip codec.
        status, ticks, channel, controller, value = struct.unpack_from('>BdBBB', raw, event_start)
        self.assertEqual((status, ticks, channel, controller, value), (0xB0, 480., 0, 11, 68))
        self.assertEqual(archive.serialize(True), raw)

    def test_truncated_midi_is_rejected(self):
        event = dict(type='note', beat=0, duration=1, channel=0, pitch=60, velocity=80)
        raw = midi_part(encode_event(event)[:-1], 1)
        archive = Archive(raw, 0, len(raw))
        with self.assertRaises(ValueError):
            parse_midi(raw, archive.root.get('MMidiPart'))

    def test_unknown_midi_status_is_rejected(self):
        event = bytearray(encode_event(dict(type='cc', beat=0, channel=0, controller=11, value=70)))
        event[0] = 0xA0
        raw = midi_part(bytes(event), 1)
        archive = Archive(raw, 0, len(raw))
        with self.assertRaises(ValueError):
            parse_midi(raw, archive.root.get('MMidiPart'))


class ArchiveTests(unittest.TestCase):
    def test_lengths_and_class_references_relocate(self):
        prefix = full('Pad', b'x')
        known_offset = len(prefix)
        known = full('Known', b'abc')
        reuse = struct.pack('>QQ', 0x8000000000000000+known_offset, 2) + b'yz'
        data = prefix + known + reuse
        a = Archive(data, 0, len(data))
        self.assertEqual(a.serialize(True), data)
        pad = a.root.get('Pad')
        pad.raw_replace(pad.data_start, pad.end, b'longer opaque payload')
        written = a.serialize(True)
        check = Archive(written, 0, len(written))
        self.assertEqual(check.serialize(True), written)
        known_nodes = [n for n in check.root.walk() if n.name == 'Known']
        self.assertEqual(len(known_nodes), 2)
        self.assertEqual(struct.unpack_from('>Q', written, known_nodes[1].start)[0],
                         0x8000000000000000+known_nodes[0].start)

    def test_object_reference_relocates(self):
        prefix = full('Pad', b'x')
        target = full('MInstrumentTrackEvent', b'abcdefghij')
        data = prefix + target
        target_body = len(data)-10
        data += struct.pack('>Q', target_body-8)
        a = Archive(data, 0, len(data))
        pad = a.root.get('Pad')
        pad.raw_replace(pad.data_start, pad.end, b'x'*37)
        out = a.serialize(True)
        check = Archive(out, 0, len(out))
        self.assertEqual(struct.unpack_from('>Q', out, len(out)-8)[0],
                         check.root.get('MInstrumentTrackEvent').data_start-8)

    def test_valid_midi_payload_is_not_scanned_as_class_handles(self):
        prefix = full('Pad', b'x')
        known_offset = len(prefix)
        known = full('Known', b'abc')
        handle = 0x8000000000000000 + known_offset
        # A valid opaque integer attribute resembles a class handle. The following
        # attribute bytes resemble a plausible 65536-byte object size. A naive
        # archive scanner would create a false object inside this long MIDI part.
        record = struct.pack('>BdBBBHI', 0xB0, 0., 0, 11, 70, 0, 3)
        record += b'GLFX' + struct.pack('>HQ', 1, handle)
        record += b'\0'*4 + struct.pack('>Hq', 1, 0)
        record += b'TDRH' + struct.pack('>Hd', 4, 70/127)
        raw = prefix + known + midi_part(record*1200, 1200)
        archive = Archive(raw, 0, len(raw))
        part = archive.root.get('MMidiPart')
        _, event_start, before = parse_midi(raw, part)
        self.assertFalse(any(event_start <= pos < part.end for pos, _ in archive.refs))
        self.assertEqual(len([n for n in archive.root.walk() if n.name=='Known']), 1)
        pad = archive.root.get('Pad')
        pad.raw_replace(pad.data_start, pad.end, b'x'*57)
        out = archive.serialize(True)
        check = Archive(out, 0, len(out))
        new_part = check.root.get('MMidiPart')
        _, new_start, after = parse_midi(out, new_part)
        compare_events(after, before)
        self.assertEqual(raw[event_start:part.end], out[new_start:new_part.end])

    def test_rif2_truncation_and_bad_lengths_are_rejected(self):
        body = b'ARCH' + struct.pack('>Q', 3) + b'abc'
        valid = b'RIF2' + struct.pack('>Q', len(body)) + b'NUND' + body
        self.assertEqual(riff_chunks(valid)[0][0], b'ARCH')
        for bad in [valid[:-1], valid[:4]+b'\0'*8+valid[12:], valid+b'!']:
            with self.subTest(length=len(bad)):
                with self.assertRaises(ValueError):
                    riff_chunks(bad)


class AttributeTests(unittest.TestCase):
    def test_opaque_state_roundtrip(self):
        fields = [Field('Name', 8, 0, '私有示例'.encode()+b'\0\xef\xbb\xbf'),
                  Field('State', 2, 7, b'\0\xff\x80opaque'),
                  Field('Nested', 2, 6, [Field('Value', 4, 0, 0.75)])]
        raw = encode_attrs(fields)
        decoded, end = read_attrs(raw, 0, len(raw))
        self.assertEqual(end, len(raw))
        self.assertEqual(encode_attrs(decoded), raw)
        self.assertEqual(text_value(decoded[0]), '私有示例')
        with self.assertRaises(ValueError):
            read_attrs(raw, 0, len(raw)-1)


if __name__ == '__main__':
    unittest.main()

"""Synthetic state and timing tests; no plug-in or commercial state is loaded."""
import importlib.util
import math
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from xml.etree import ElementTree as ET

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import offline_render as offline


def preset(chunks=((b'Comp', b'component'), (b'Cont', b'controller'))):
    """Build a synthetic version-one preset with a trailing chunk list."""
    body, entries = bytearray(), bytearray()
    for tag, payload in chunks:
        entries += struct.pack('<4sqq', tag, 48 + len(body), len(payload))
        body += payload
    header = b'VST3' + struct.pack('<I', 1) + b'0123456789abcdef' * 2
    return header + struct.pack('<Q', 48 + len(body)) + body + b'List' + struct.pack('<I', len(chunks)) + entries


def note(**changes):
    result = dict(type='note', beat=0, channel=0, pitch=60, velocity=100, duration=1)
    result.update(changes)
    return result


class StateTests(unittest.TestCase):
    def test_juce_memory_block_encoding_and_xml_envelope(self):
        data = offline.make_vst3_raw_state(b'\x01\x02\x03', b'\xff')
        self.assertEqual(data[:4], b'VC2!')
        length = struct.unpack_from('<I', data, 4)[0]
        self.assertEqual(len(data), length + 9)
        self.assertEqual(data[-1:], b'\0')
        root = ET.fromstring(data[8:8 + length])
        self.assertEqual(root.tag, 'VST3PluginState')
        self.assertEqual(root.findtext('IComponent'), '3.AHv.')
        self.assertEqual(root.findtext('IEditController'), '1.+C')
        empty = offline.make_vst3_raw_state(b'')
        self.assertEqual(ET.fromstring(empty[8:-1]).findtext('IComponent'), '0.')
        self.assertEqual(ET.fromstring(empty[8:-1]).findtext('IEditController'), '0.')

    def test_non_bytes_state_is_rejected(self):
        for value in ('text', [1], None):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                offline.make_vst3_raw_state(value)

    def test_preset_preserves_unknown_chunks_and_uid(self):
        uid, chunks = offline.split_vst3_preset(preset(((b'Comp', b'abc'), (b'Info', b'xyz'), (b'Cont', b''))))
        self.assertEqual(uid, '0123456789abcdef' * 2)
        self.assertEqual(chunks, {'Comp': b'abc', 'Info': b'xyz', 'Cont': b''})

    def test_bad_preset_header_and_list(self):
        valid = preset()
        list_offset = struct.unpack_from('<Q', valid, 40)[0]
        cases = [b'', valid[:47], b'FAIL' + valid[4:], valid[:4] + struct.pack('<I', 2) + valid[8:],
                 valid[:8] + b'G' + valid[9:], valid[:8] + b'\xff' + valid[9:], valid[:-1]]
        for pointer in (0, 47, len(valid), (1 << 64) - 1):
            bad = bytearray(valid)
            struct.pack_into('<Q', bad, 40, pointer)
            cases.append(bytes(bad))
        bad = bytearray(valid)
        bad[list_offset:list_offset + 4] = b'Nope'
        cases.append(bytes(bad))
        bad = bytearray(valid)
        struct.pack_into('<I', bad, list_offset + 4, 0xffffffff)
        cases.append(bytes(bad))
        for data in cases:
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                offline.split_vst3_preset(data)

    def test_bad_chunk_boundaries_duplicates_and_overlap(self):
        valid = preset()
        table = struct.unpack_from('<Q', valid, 40)[0]
        cases = [preset(((b'Comp', b'a'), (b'Comp', b'b')))]
        for offset, size in ((47, 1), (-1, 1), (48, -1), (48, len(valid)), (table, 4), (len(valid), 1)):
            bad = bytearray(valid)
            struct.pack_into('<qq', bad, table + 12, offset, size)
            cases.append(bytes(bad))
        bad = bytearray(valid)
        struct.pack_into('<q', bad, table + 32, 49)
        cases.append(bytes(bad))
        for data in cases:
            with self.subTest(data_length=len(data)), self.assertRaises(ValueError):
                offline.split_vst3_preset(data)

    def test_import_needs_only_standard_library(self):
        code = """import builtins, sys
sys.path.insert(0, sys.argv[1])
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'numpy', 'pedalboard', 'music_timeline'}:
        raise AssertionError('Unexpected dependency: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import offline_render
offline_render.make_vst3_raw_state(b'abc')
offline_render.schedule_midi([], lambda beat: beat, 1)
"""
        result = subprocess.run([sys.executable, '-c', code, str(SCRIPTS)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class ScheduleTests(unittest.TestCase):
    def test_absolute_project_beats_and_note_end_use_callback(self):
        messages, report = offline.schedule_midi([note(beat=3, duration=2)], lambda b: b / 2 if b < 4 else 2 + b - 4, 6)
        self.assertEqual(messages, [(bytes([0x90, 60, 100]), 1.5), (bytes([0x80, 60, 64]), 3.0)])
        self.assertEqual(report['end_seconds'], 4)
        self.assertEqual(report['message_count'], 2)

    @unittest.skipUnless((SCRIPTS / 'music_timeline.py').exists(), 'TempoMap is optional')
    def test_tempo_ramp_uses_integrated_time(self):
        from music_timeline import TempoMap
        tempo = TempoMap([dict(beat=0, bpm=60, curve='step'), dict(beat=4, bpm=120, curve='linear')])
        messages, _ = offline.schedule_midi([note(beat=1, duration=3)], tempo.beat_to_seconds, 5)
        self.assertAlmostEqual(messages[0][1], 4 * math.log(1.25))
        self.assertAlmostEqual(messages[1][1], 4 * math.log(2))

    def test_simultaneous_off_controls_program_bend_on_order(self):
        events = [note(beat=1), dict(type='cc', beat=1, channel=2, controller=0, value=9),
                  dict(type='program', beat=1, channel=2, program=4), note(),
                  dict(type='pitchbend', beat=1, channel=2, value=-8192),
                  dict(type='cc', beat=1, channel=2, controller=32, value=3)]
        messages, _ = offline.schedule_midi(events, lambda b: b, 3)
        at_one = [raw for raw, time in messages if time == 1]
        self.assertEqual(at_one, [bytes([0x80, 60, 64]), bytes([0xB2, 0, 9]), bytes([0xC2, 4]),
                                  bytes([0xE2, 0, 0]), bytes([0xB2, 32, 3]), bytes([0x90, 60, 100])])
        self.assertEqual(len(messages), 8)  # No implicit panic/controller messages.

    def test_normalized_velocity_and_release_quantization_report(self):
        events = [note(velocity_normalized=.5, release_normalized=.25),
                  note(beat=1, velocity_normalized=1, release_velocity_normalized=1)]
        messages, report = offline.schedule_midi(events, lambda b: b, 3)
        self.assertEqual(messages[0][0][-1], 64)
        self.assertEqual(messages[1][0][-1], 32)
        self.assertEqual(messages[2][0][-1], 127)
        self.assertEqual(messages[3][0][-1], 127)
        self.assertAlmostEqual(report['max_velocity_error'], abs(64 / 127 - .5))
        self.assertAlmostEqual(report['max_release_error'], abs(32 / 127 - .25))
        self.assertEqual(report['normalized_velocity_count'], 2)
        self.assertEqual(report['normalized_release_count'], 2)
        normalized_only = note(velocity_normalized=.8, release_velocity_normalized=0)
        del normalized_only['velocity']
        messages, _ = offline.schedule_midi([normalized_only], lambda b: b, 2)
        self.assertEqual([message[-1] for message, _ in messages], [102, 0])
        messages, report = offline.schedule_midi([note(velocity_normalized=.0001)], lambda b: b, 2)
        self.assertEqual(messages[0][0][-1], 1)
        self.assertAlmostEqual(report['max_velocity_error'], 1 / 127 - .0001)

    def test_pitch_bend_endpoints(self):
        messages, _ = offline.schedule_midi([dict(type='pitchbend', beat=0, channel=15, value=v)
                                             for v in (-8192, 0, 8191)], lambda b: b, 1)
        self.assertEqual([raw for raw, _ in messages], [b'\xef\x00\x00', b'\xef\x00\x40', b'\xef\x7f\x7f'])

    def test_positive_normalized_velocity_overrides_zero_coarse_value(self):
        messages, report = offline.schedule_midi([note(velocity=0, velocity_normalized=.0001)], lambda b: b, 2)
        self.assertEqual(messages[0][0], bytes([0x90, 60, 1]))
        self.assertAlmostEqual(report['max_velocity_error'], 1 / 127 - .0001)
        for velocity in (-1, 128, True):
            with self.subTest(velocity=velocity), self.assertRaises(ValueError):
                offline.schedule_midi([note(velocity=velocity, velocity_normalized=.5)], lambda b: b, 2)

    def test_unsupported_or_invalid_events_fail_explicitly(self):
        cases = [note(duration=0), note(duration=-1), note(beat=-1), note(duration=4), note(channel=16),
                 note(pitch=128), note(velocity=0), note(velocity=128), note(velocity=True), note(beat=math.nan),
                 note(velocity_normalized=0), note(velocity_normalized=1.01),
                 note(release_velocity=128), note(release_normalized=-.1), note(release_normalized=.2, release_velocity_normalized=.3),
                 note(type='sysex'), note(offset=10), {'type': 'note'},
                 dict(type='cc', beat=0, channel=0, controller=1, value=128),
                 dict(type='program', beat=0, channel=0, program=-1),
                 dict(type='pitchbend', beat=0, channel=0, value=8192)]
        for event in cases:
            with self.subTest(event=event), self.assertRaises(ValueError):
                offline.schedule_midi([event], lambda b: b, 3)

    def test_invalid_tempo_callback_or_end_fails(self):
        for callback in (lambda b: math.nan, lambda b: -b, lambda b: 0, lambda b: True):
            with self.subTest(callback=callback), self.assertRaises(ValueError):
                offline.schedule_midi([note()], callback, 2)
        for end in (-1, 0, math.inf, True):
            with self.subTest(end=end), self.assertRaises(ValueError):
                offline.schedule_midi([], lambda b: b, end)


class BlockTests(unittest.TestCase):
    def test_half_open_boundaries_tail_and_partial_block(self):
        messages = [(b'\x90\x3c\x64', 0), (b'\xb0\x01\x40', .25), (b'\x80\x3c\x00', .5)]
        blocks = list(offline.iter_midi_blocks(messages, 11, 8, 2))
        self.assertEqual([n for n, _ in blocks], [2, 2, 2, 2, 2, 1])
        self.assertEqual([m for _, m in blocks[:3]], [[(messages[0][0], 0)], [(messages[1][0], 0)], [(messages[2][0], 0)]])
        self.assertTrue(all(not m for _, m in blocks[3:]))

    def test_sample_boundary_at_noninteger_rate(self):
        boundary = 512 / 44100
        blocks = list(offline.iter_midi_blocks([(b'\xb0\x01\x40', boundary)], 1024, 44100, 512))
        self.assertEqual(blocks[0][1], [])
        self.assertEqual(blocks[1][1], [(b'\xb0\x01\x40', 0)])

    def test_final_boundary_rejected_before_first_block(self):
        iterator = offline.iter_midi_blocks([(b'\x90\x3c\x64', 0), (b'\x80\x3c\x40', 1)], 100, 100, 10)
        with self.assertRaisesRegex(ValueError, 'boundary|duration|total_frames'):
            next(iterator)

    def test_invalid_messages_or_unsorted_input(self):
        cases = [[(b'\x90\x3c\x64', -.1)], [(b'\x90\x3c\x64', math.nan)], [(b'\x90\x3c', 0)],
                 [(b'\x90\x80\x64', 0)], [(b'\xf0\x01\xf7', 0)], [(b'\xc0\x01\x00', 0)],
                 [(b'\xb0\x01\x01', .5), (b'\xb0\x01\x00', .4)], [('not bytes', 0)]]
        for messages in cases:
            with self.subTest(messages=messages), self.assertRaises(ValueError):
                list(offline.iter_midi_blocks(messages, 10, 10, 5))
        for total, rate, block in ((-1, 8, 2), (1.5, 8, 2), (1, 0, 2), (1, math.nan, 2), (1, 8, 0)):
            with self.subTest(args=(total, rate, block)), self.assertRaises(ValueError):
                list(offline.iter_midi_blocks([], total, rate, block))
        self.assertEqual(list(offline.iter_midi_blocks([], 0, 8, 2)), [])


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'Audio tests require numpy')
class RenderTests(unittest.TestCase):
    def test_persistent_fake_instrument_and_cross_block_controls(self):
        import numpy as np

        class Instrument:
            def __init__(self):
                self.active, self.gain, self.calls = False, 1., []

            def __call__(self, messages, *, duration, sample_rate, num_channels, buffer_size, reset):
                self.calls.append((duration, reset, buffer_size, list(messages)))
                frames = round(duration * sample_rate)
                output = np.zeros((num_channels, frames), dtype=np.float64)
                grouped = {}
                for raw, time in messages:
                    grouped.setdefault(round(time * sample_rate), []).append(raw)
                for frame in range(frames):
                    for raw in grouped.get(frame, []):
                        if raw[0] & 0xf0 == 0x90:
                            self.active = True
                        elif raw[0] & 0xf0 == 0x80:
                            self.active = False
                        elif raw[0] & 0xf0 == 0xb0:
                            self.gain = raw[2] / 127
                    output[:, frame] = self.gain if self.active else 0
                return output

        instrument = Instrument()
        messages = [(b'\x90\x3c\x64', 0), (b'\xb0\x07\x40', .5), (b'\x80\x3c\x40', .75)]
        audio = offline.render_instrument(instrument, messages, 10, 8, 2, buffer_size=64)
        self.assertEqual(audio.shape, (2, 10))
        self.assertEqual(audio.dtype, np.float32)
        np.testing.assert_allclose(audio[0], [1] * 4 + [64 / 127] * 2 + [0] * 4)
        self.assertEqual(len(instrument.calls), 5)
        self.assertTrue(all(reset is False and buffer == 64 for _, reset, buffer, _ in instrument.calls))
        self.assertEqual([len(messages) for _, _, _, messages in instrument.calls], [1, 0, 1, 1, 0])

    def test_invalid_plugin_audio_is_rejected(self):
        import numpy as np
        for result in (np.zeros((1, 2)), np.zeros((2, 3)), np.ones((2, 2)) * np.nan,
                       np.ones((2, 2)) * np.inf, np.ones((2, 2)) * 1e100,
                       np.ones((2, 2), dtype=complex), [['x', 'x'], ['x', 'x']]):
            with self.subTest(shape=np.shape(result)), self.assertRaises(ValueError):
                offline.render_instrument(lambda *a, **k: result, [], 2, 8, 2)

    def test_bad_schedule_does_not_call_plugin(self):
        calls = []
        with self.assertRaises(ValueError):
            offline.render_instrument(lambda *a, **k: calls.append(k), [(b'\x80\x3c\x40', 1)], 8, 8, 2)
        self.assertEqual(calls, [])


class GainTests(unittest.TestCase):
    def test_observed_fader_anchors(self):
        for raw, gain in ((0, 0), (18688, .5), (25856, 1), (32767, 2)):
            self.assertAlmostEqual(offline.cubase15_fader_gain(raw), gain)
        self.assertLess(offline.cubase15_fader_gain(18687), .5)
        self.assertGreater(offline.cubase15_fader_gain(25857), 1)

    def test_observed_input_gain_anchors(self):
        self.assertEqual(offline.cubase15_input_gain(0), 0)
        self.assertAlmostEqual(offline.cubase15_input_gain(32767), 256)
        self.assertAlmostEqual(offline.cubase15_input_gain(16383) * offline.cubase15_input_gain(16384), 1)

    def test_fractional_gain_coordinates(self):
        self.assertAlmostEqual(offline.cubase15_fader_gain(22272.5), .75 + .5 / 14336)
        self.assertAlmostEqual(offline.cubase15_fader_gain(30000.5), 1 + (30000.5 - 25856) / 6911)
        self.assertAlmostEqual(offline.cubase15_input_gain(16383.5), 1.)

    def test_out_of_range_gain_is_rejected(self):
        for function in (offline.cubase15_fader_gain, offline.cubase15_input_gain):
            for raw in (-1, 32768, True, math.nan, math.inf):
                with self.subTest(function=function, raw=raw), self.assertRaises(ValueError):
                    function(raw)


if __name__ == '__main__':
    unittest.main()

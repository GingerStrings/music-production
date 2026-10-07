"""Notation invariants verified with synthetic music; no private score required."""
import copy
from fractions import Fraction
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from engrave import validate, make_sources, notation_voices, pitch, export, split_rhythm


def example():
    return dict(schema_version=1, kind='notation', title='Synthetic notation',
                bars=[dict(meter=[4,4], key=dict(step='C', alter=0, mode='major'), tempo=120), {}],
                parts=[dict(id='part', name='Instrument', short_name='Inst.', clef='treble', notes=[
                    dict(id='a', beat='7/2', duration='3/2', pitches=[dict(step='C', alter=0, octave=4)],
                         slur_start=True),
                    dict(id='b', beat=5, duration=1, pitches=[dict(step='D', alter=0, octave=4)],
                         slur_end=True)])])


def piano_example():
    data = example()
    lead = copy.deepcopy(data['parts'][0]['notes'])
    data['schema_version'] = 2
    data['parts'] = [dict(id='piano', name='Piano', short_name='Pno.', group='piano',
                         staves=[dict(id='upper', clef='treble', voices=[
                             dict(id='melody', notes=lead),
                             dict(id='inner', notes=[dict(id='a', beat='7/2', duration='5/2',
                                  pitches=[dict(step='C', alter=0, octave=4)])])]),
                                 dict(id='lower', clef='bass', voices=[dict(id='bass', notes=[])])],
                         dynamics=[dict(beat=0, dynamic='p', hairpin='<'), dict(beat=4, dynamic='mf')],
                         pedal=[dict(beat=0, action='down'), dict(beat=4, action='change'),
                                dict(beat=8, action='up')])]
    return data


class NotationTests(unittest.TestCase):
    def test_absolute_octaves_and_enharmonics(self):
        self.assertEqual(pitch(dict(step='C', alter=0, octave=4)), ("c'", 60))
        self.assertEqual(pitch(dict(step='B', alter=1, octave=3))[1], 60)
        self.assertEqual(pitch(dict(step='C', alter=-1, octave=4))[1], 59)

    def test_cross_bar_tie_preserves_onset_duration_and_slur_end(self):
        sources, report = make_sources(example())
        a = [n for n in report['fragments']['part'] if n['id']=='a']
        self.assertEqual([n['bar'] for n in a], [1,2])
        self.assertEqual([n['duration'] for n in a], ['1/2','1'])
        self.assertFalse(a[0]['tie_in']); self.assertTrue(a[0]['tie_out'])
        self.assertTrue(a[1]['tie_in']); self.assertFalse(a[1]['tie_out'])
        self.assertIn("c'8~(", sources['music.ily'])

    def test_key_meter_and_tempo_changes_preserve_exact_music_positions(self):
        data = example()
        data['bars'][1] = dict(meter=[3,4], key=dict(step='G', alter=0, mode='minor'), tempo=90)
        times, _ = validate(data)
        self.assertEqual(times, [0,4,7])
        sources, report = make_sources(data)
        self.assertEqual(report['quarters'], '7')
        self.assertIn('\\key g \\minor', sources['music.ily'])

    def test_shortened_performance_gate_is_not_silently_quantized(self):
        data = example(); data['parts'][0]['notes'][0]['duration'] = .425
        with self.assertRaisesRegex(ValueError, 'explicit rhythmic adaptation'):
            validate(data)

    def test_unknown_performance_fields_and_overlaps_are_rejected(self):
        data = example(); data['parts'][0]['notes'][0]['trigger_beat'] = 3.4
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            validate(data)
        data = example(); data['parts'][0]['notes'][1]['beat'] = 4
        with self.assertRaisesRegex(ValueError, 'Overlap'):
            validate(data)

    def test_unclosed_notation_is_rejected(self):
        data = example(); del data['parts'][0]['notes'][1]['slur_end']
        with self.assertRaisesRegex(ValueError, 'Unclosed'):
            validate(data)

    def test_chord_pitch_count_and_empty_part_rests(self):
        data = example()
        data['parts'][0]['notes'][1]['pitches'].append(dict(step='F',alter=1,octave=4))
        data['parts'].append(dict(id='silent',name='Silent',short_name='S.',clef='bass',notes=[]))
        sources, report = make_sources(data)
        self.assertEqual(report['parts'][0]['pitches'], 3)
        self.assertIn('R1*1', sources['music.ily'])
        self.assertEqual(report['parts'][1]['events'], 0)

    def test_offbeat_duration_keeps_beat_boundary_visible(self):
        self.assertEqual(split_rhythm(Fraction(1,2), Fraction(3,2)), [Fraction(1,2),1])
        self.assertEqual(split_rhythm(0, Fraction(3,2)), [Fraction(3,2)])

    def test_output_is_new_and_failed_compilation_does_not_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'new'
            with self.assertRaises(OSError):
                export(example(), out, str(Path(tmp)/'missing-lilypond'))
            self.assertFalse(out.exists())
            export(example(), out)
            before = (out/'music.ily').read_bytes()
            with self.assertRaises(FileExistsError):
                export(example(), out)
            self.assertEqual(before, (out/'music.ily').read_bytes())


class PianoNotationTests(unittest.TestCase):
    def test_independent_unisons_and_crossbar_durations_keep_voice_identity(self):
        data = piano_example()
        _, report = make_sources(data)
        voices = list(notation_voices(data))
        self.assertEqual([v['id'] for v in voices],
                         ['piano/upper/melody', 'piano/upper/inner', 'piano/lower/bass'])
        self.assertEqual(report['parts'][0]['events'], 3)
        self.assertEqual(report['parts'][0]['staves'], 2)
        for ident, expected in [('piano/upper/melody', Fraction(3, 2)),
                                ('piano/upper/inner', Fraction(5, 2))]:
            fragments = [f for f in report['fragments'][ident] if f['id'] == 'a']
            self.assertEqual(sum(Fraction(f['duration']) for f in fragments), expected)
            self.assertEqual(Fraction(fragments[0]['beat']), Fraction(7, 2))
            self.assertEqual([f['bar'] for f in fragments], [1, 2])
        self.assertEqual(report['fragments']['piano/lower/bass'], [])

    def test_overlap_is_rejected_only_within_the_same_voice(self):
        data = piano_example()
        validate(data)
        data['parts'][0]['staves'][0]['voices'][0]['notes'][1]['beat'] = 4
        with self.assertRaisesRegex(ValueError, 'Overlap'):
            validate(data)

    def test_ambiguous_staff_voice_and_legacy_fields_are_rejected(self):
        for kind in ('staff_id', 'voice_id', 'voice_number', 'legacy_notes', 'group'):
            with self.subTest(kind=kind):
                data = piano_example(); part = data['parts'][0]
                if kind == 'staff_id':
                    part['staves'][1]['id'] = 'upper'
                elif kind == 'voice_id':
                    part['staves'][0]['voices'][1]['id'] = 'melody'
                elif kind == 'voice_number':
                    part['staves'][0]['voices'][1]['voice_number'] = 1
                elif kind == 'legacy_notes':
                    part['notes'] = []
                else:
                    part['group'] = 'staff'
                with self.assertRaises(ValueError):
                    validate(data)

    def test_pedal_must_have_ordered_valid_transitions_and_release(self):
        for pedal in ([dict(beat=0, action='up')],
                      [dict(beat=0, action='down')],
                      [dict(beat=0, action='down'), dict(beat=1, action='down')],
                      [dict(beat=0, action='change')],
                      [dict(beat=0, action='down'), dict(beat=0, action='up')],
                      [dict(beat=0, action='down'), dict(beat=9, action='up')]):
            with self.subTest(pedal=pedal):
                data = piano_example(); data['parts'][0]['pedal'] = pedal
                with self.assertRaises(ValueError):
                    validate(data)
        validate(piano_example())  # Includes same-time repedalling and final-bar release.

    def test_shared_dynamics_are_independent_of_note_onsets(self):
        data = piano_example()
        data['parts'][0]['dynamics'] = [dict(beat='1/2', dynamic='p', hairpin='<'),
                                      dict(beat='5/2', hairpin_stop=True)]
        validate(data)
        data['parts'][0]['dynamics'].pop()
        with self.assertRaisesRegex(ValueError, 'Unclosed'):
            validate(data)


if __name__ == '__main__':
    unittest.main()

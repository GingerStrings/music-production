"""Synthetic invariants for tempo maps, extended MIDI and explicit repair."""
import copy
import io
import math
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from music_timeline import TempoMap,validate_meters
from music_data import validate_performance,compile_score
from cpr_archive import Archive
from cpr_midi import parse_midi,encode_event,compare_events
from cpr_timeline import read_tempo,write_tempo
from midi_import import repair_pitch_overflow,smf_channel_records,import_midi
from test_tools import full,midi_part,example


class TimelineTests(unittest.TestCase):
    def test_step_crossing_and_inverse(self):
        t=TempoMap([dict(beat=0,bpm=120,curve='step'),dict(beat=4,bpm=60,curve='step')])
        self.assertEqual(t.beat_to_seconds(5),3)
        self.assertAlmostEqual(t.advance(4.1,200),3.8)
        for beat in (0,.1,3.9,4,4.1,100):
            self.assertAlmostEqual(t.seconds_to_beat(t.beat_to_seconds(beat)),beat)

    def test_linear_bpm_uses_integral(self):
        t=TempoMap([dict(beat=0,bpm=60,curve='step'),dict(beat=4,bpm=120,curve='linear')])
        self.assertAlmostEqual(t.beat_to_seconds(4),4*math.log(2))
        for beat in (0,.1,1,3.9,4,40):self.assertAlmostEqual(t.seconds_to_beat(t.beat_to_seconds(beat)),beat)

    def test_signature_bar_positions(self):
        points=[dict(beat=0,numerator=2,denominator=4),dict(beat=2,numerator=4,denominator=4),dict(beat=578,numerator=1,denominator=4)]
        self.assertEqual([p['bar'] for p in validate_meters(points)],[0,1,145])
        points[1]['beat']=1
        with self.assertRaises(ValueError):validate_meters(points)

    def test_invalid_timelines(self):
        for points in ([],[dict(beat=1,bpm=120,curve='step')],
                       [dict(beat=0,bpm=0,curve='step')],
                       [dict(beat=0,bpm=120,curve='linear')]):
            with self.subTest(points=points):
                with self.assertRaises(ValueError):TempoMap(points)

    def test_score_compilation_crosses_tempo_boundary(self):
        score=example();score.update(schema_version=2,preroll_beats=0,end_beats=10,
            tempo_map=[dict(beat=0,bpm=120,curve='step'),dict(beat=4,bpm=60,curve='step')],
            meter_map=[dict(beat=0,numerator=4,denominator=4)])
        del score['bpm'];del score['meter']
        score['tracks']=[dict(template_index=1,controllers=[],notes=[dict(beat=4.1,duration=1,pitch=60,velocity=80,
            advance_ms=200,release_advance_ms=100,timing_basis='estimated')])]
        n=compile_score(score)['tracks'][0]['events'][0]
        self.assertAlmostEqual(n['beat'],3.8)
        self.assertAlmostEqual(n['beat']+n['duration'],5)

    def test_native_tempo_cache_and_backup_are_updated(self):
        track_properties=struct.pack('>I4sHI',1,b'TEST',8,7)+b'opaque\0'
        payload=struct.pack('>IfddHfH',1,.5,0,0,0,120,1)+track_properties+bytes(4)
        raw=full('MTempoTrackEvent',payload,version=3)
        a=Archive(raw,0,len(raw));node=a.root.get('MTempoTrackEvent')
        points=[dict(beat=0,bpm=76,curve='step'),dict(beat=4,bpm=32,curve='step')]
        write_tempo(raw,node,points);out=a.serialize(True)
        b=Archive(out,0,len(out));actual,_,mode=read_tempo(out,b.root.get('MTempoTrackEvent'))
        self.assertEqual(len(actual),2);self.assertFalse(mode['fixed_tempo'])
        self.assertAlmostEqual(mode['fallback_bpm'],76)
        self.assertTrue(out.endswith(track_properties+bytes(8)))
        self.assertEqual(mode['point_property_maps'],2)
        _,seconds,ticks,shape=struct.unpack_from('>fddH',out,b.root.get('MTempoTrackEvent').data_start+26)
        self.assertEqual((ticks,shape),(1920,0))
        self.assertAlmostEqual(seconds,4*60/76,places=6)


class ExtendedMidiTests(unittest.TestCase):
    def test_pitch_bend_bytes_and_roundtrip(self):
        events=[dict(type='pitchbend',beat=i,channel=3,value=v) for i,v in enumerate((-8192,-127,0,127,8191))]
        for e in events:
            raw=encode_event(e);status,tick,ch,lo,hi=struct.unpack_from('>BdBBB',raw)
            self.assertEqual((status,tick,ch),(0xe0,e['beat']*480,3))
            self.assertEqual(lo+hi*128-8192,e['value'])
            self.assertEqual(len(raw),32)
        raw=midi_part(b''.join(encode_event(e) for e in events),len(events))
        a=Archive(raw,0,len(raw));compare_events(parse_midi(raw,a.root.get('MMidiPart'))[2],events)

    def test_empty_part_without_flag(self):
        raw=full('MMidiPart',struct.pack('>I',2)+b'x\0'+bytes(20)+bytes(4))
        a=Archive(raw,0,len(raw));self.assertEqual(parse_midi(raw,a.root.get('MMidiPart'))[2],[])

    def test_release_velocity_and_zero_length_are_preserved(self):
        events=[dict(type='note',beat=0,channel=0,pitch=60,velocity=80,duration=0,release_velocity=0)]
        raw=midi_part(encode_event(events[0]),1);a=Archive(raw,0,len(raw))
        compare_events(parse_midi(raw,a.root.get('MMidiPart'))[2],events)

    def test_repair_preserves_bend_amplitude_and_other_bytes(self):
        body=(b'\x00\xb0\x65\x00\x00\xb0\x64\x00\x00\xb0\x06\x0c'
              b'\x00\xe0\x00\x40\x10\xe0\x40\x88\x10\xe0\x00\x00\x00\xff\x2f\x00')
        raw=b'MThd'+struct.pack('>IHHH',6,0,1,480)+b'MTrk'+struct.pack('>I',len(body))+body
        with self.assertRaises(ValueError):repair_pitch_overflow(raw)
        out,report=repair_pitch_overflow(raw,True)
        self.assertEqual(report['invalid_events'],1)
        self.assertEqual(report['repairs'][0]['new_range_semitones'],24)
        before=smf_channel_records(raw);after=smf_channel_records(out)
        for a,b in zip(before,after):
            if a['status']==0xe0:
                x=a['data'][0]+128*a['data'][1]-8192;y=b['data'][0]+128*b['data'][1]-8192
                self.assertLessEqual(abs(x*12-y*24)/8192*100,.147)
            elif a['data'][0]!=6:self.assertEqual(a,b)
        self.assertEqual(out[-4:],raw[-4:])

    def test_invalid_non_bend_is_not_repaired(self):
        body=b'\x00\x90\x40\xff\x00\xff\x2f\x00'
        raw=b'MThd'+struct.pack('>IHHH',6,0,1,480)+b'MTrk'+struct.pack('>I',len(body))+body
        with self.assertRaises(ValueError):repair_pitch_overflow(raw,True)


if __name__=='__main__':unittest.main()

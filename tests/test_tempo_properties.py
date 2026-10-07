"""Regression for v3 tempo tables whose point-property maps were omitted."""
import struct
import unittest

from test_tools import full
from cpr_archive import Archive
from cpr_timeline import read_tempo, write_tempo


def payload(count, version=3, track=bytes(4), point_maps=None):
    table = struct.pack('>I', count) + b''.join(
        struct.pack('>fddH', .5, i*2., i*1920., 0) for i in range(count))
    if point_maps is None:
        point_maps = bytes(4*count) if version == 3 else b''
    return table + struct.pack('>fH', 120., 0) + track + point_maps


def parse(raw):
    archive = Archive(raw, 0, len(raw))
    return archive, archive.root.get('MTempoTrackEvent')


def resize(raw, count):
    archive, node = parse(raw)
    write_tempo(raw, node, [dict(beat=i*4, bpm=120, curve='step') for i in range(count)])
    return archive.serialize(True)


class TempoPropertiesTests(unittest.TestCase):
    def test_one_to_eight_points_adds_seven_empty_maps(self):
        raw = full('MTempoTrackEvent', payload(1), version=3)
        out = resize(raw, 8)
        _, node = parse(out)
        points, tail, mode = read_tempo(out, node)
        self.assertEqual(len(points), 8)
        self.assertEqual(mode['point_property_maps'], 8)
        self.assertEqual(out[tail+6:node.end], bytes(36))
        self.assertEqual(len(out)-len(raw), 7*(22+4))

    def test_eight_to_one_points_removes_old_maps(self):
        raw = full('MTempoTrackEvent', payload(8), version=3)
        out = resize(raw, 1)
        self.assertEqual(out, full('MTempoTrackEvent', payload(1), version=3))

    def test_old_writer_missing_seven_maps_is_rejected(self):
        raw = full('MTempoTrackEvent', payload(8, point_maps=bytes(4)), version=3)
        archive, node = parse(raw)
        with self.assertRaisesRegex(ValueError, 'tempo point 2 properties'):
            read_tempo(raw, node)
        with self.assertRaisesRegex(ValueError, 'tempo point 2 properties'):
            write_tempo(raw, node, [dict(beat=0, bpm=120, curve='step')])
        self.assertEqual(archive.serialize(), raw)

    def test_trailing_bytes_and_truncated_string_are_rejected(self):
        malformed = [payload(1)+bytes(4),
                     payload(1, point_maps=struct.pack('>I4sHI',1,b'TEST',8,100)+b'x')]
        for body in malformed:
            with self.subTest(body=body):
                raw = full('MTempoTrackEvent',body,version=3)
                _, node = parse(raw)
                with self.assertRaises(ValueError):read_tempo(raw,node)

    def test_global_object_properties_survive_resizing(self):
        label = b'TempoPropertyBase\0'
        base = b'\xff'*7+b'\xfe'+struct.pack('>I',len(label))+label+bytes(2)
        obj = full('TempoPropertyObject', bytes(4))
        track = struct.pack('>I4sH',1,b'VARI',2)+base+obj
        raw = full('MTempoTrackEvent',payload(1,track=track),version=3)
        out = resize(raw,8)
        archive,node = parse(out)
        _,tail,_ = read_tempo(out,node)
        self.assertEqual(out[tail+6:node.end],track+bytes(32))
        self.assertEqual(archive.serialize(True),out)
        self.assertEqual(node.get('TempoPropertyObject').class_version,0)

    def test_nonempty_point_properties_preserved_or_explicitly_rejected(self):
        point = struct.pack('>I4sHI',1,b'TEST',8,5)+b'name\0'
        raw = full('MTempoTrackEvent',payload(1,point_maps=point),version=3)
        archive,node = parse(raw)
        write_tempo(raw,node,[dict(beat=0,bpm=60,curve='step')])
        out = archive.serialize(True)
        _,new = parse(out)
        self.assertEqual(read_tempo(out,new)[0][0]['bpm'],60)
        self.assertTrue(out.endswith(point))
        with self.assertRaisesRegex(ValueError,'nonempty point properties'):
            resize(raw,2)

    def test_reused_class_inherits_tempo_version(self):
        body = payload(1)
        first = full('MTempoTrackEvent',body,version=3)
        raw = first + struct.pack('>QQ',0x8000000000000000,len(body))+body
        archive = Archive(raw,0,len(raw))
        nodes = [n for n in archive.root.walk() if n.name=='MTempoTrackEvent']
        self.assertEqual([n.class_version for n in nodes],[3,3])
        self.assertEqual([read_tempo(raw,n)[2]['point_property_maps'] for n in nodes],[1,1])
        self.assertEqual(archive.serialize(True),raw)

    def test_version_two_has_no_per_point_maps(self):
        raw = full('MTempoTrackEvent',payload(1,version=2),version=2)
        out = resize(raw,8)
        _,node = parse(out)
        _,tail,mode = read_tempo(out,node)
        self.assertEqual(mode['point_property_maps'],0)
        self.assertEqual(out[tail+6:node.end],bytes(4))

    def test_unknown_tempo_version_is_rejected(self):
        raw = full('MTempoTrackEvent',payload(1),version=4)
        _,node = parse(raw)
        with self.assertRaisesRegex(ValueError,'class version: 4'):
            read_tempo(raw,node)


if __name__ == '__main__':unittest.main()

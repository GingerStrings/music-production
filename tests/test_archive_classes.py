"""Archive registration and opaque-state regressions, without vendor data."""
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cpr_archive import Archive, Raw
from cpr_fields import Field, encode_attrs, read_attrs
from test_tools import full


def declaration(name, version=0):
    label = name.encode() + b'\0'
    return b'\xff'*7+b'\xfe'+struct.pack('>I', len(label))+label+struct.pack('>H', version)


class ArchiveClassTests(unittest.TestCase):
    def test_drum_name_boundary_is_not_an_object_reference(self):
        name = b'Maple Tree\0'
        notation = b'instrument.example\0\xef\xbb\xbf'
        technique = b'pt.example\0\xef\xbb\xbf'
        drum = (bytes(29)+struct.pack('>I',len(name))+name+struct.pack('>II',28,len(notation))
                +notation+struct.pack('>I',len(technique))+technique)
        # Three zero scalar bytes + uint32 name length + 'M' happen to equal
        # the target's archive-relative address. This is ordinary text data.
        accidental = struct.unpack_from('>Q',drum,26)[0]
        target = full('MSignatureTrackEvent',b'y')
        pad_size = accidental+8-len(full('Pad',b''))-len(full('MSignatureTrackEvent',b''))
        raw = (full('Pad',b'x'*pad_size)+target+full('PDrumMapEntry',drum,version=3)
               +full('Holder',struct.pack('>Q',accidental)))
        archive = Archive(raw,0,len(raw))
        self.assertEqual(len(archive.object_refs),1)
        pad = archive.root.get('Pad')
        pad.raw_replace(pad.data_start,pad.end,b'x'*(pad_size+28))
        out = archive.serialize(True)
        check = Archive(out,0,len(out))
        entry = check.root.get('PDrumMapEntry')
        self.assertEqual(out[entry.data_start:entry.end],drum)
        holder = check.root.get('Holder')
        self.assertEqual(struct.unpack_from('>Q',out,holder.data_start)[0],accidental+28)

    def test_attribute_minus_one_is_not_a_class_declaration(self):
        fields = [Field('Unused', 1, 0, -1), Field('SummingMode', 1, 0, 1), Field('Next', 1, 0, 0)]
        raw = full('FAttributes', encode_attrs(fields))
        archive = Archive(raw, 0, len(raw))
        self.assertEqual([v[0] for v in archive.classes.values()], ['FAttributes'])
        self.assertEqual(archive.serialize(True), raw)

    def test_opaque_plugin_class_and_reference_bytes_do_not_relocate(self):
        prefix = full('Pad', b'x')
        known = full('Known', b'y')
        state = full('VendorPrivateClass', b'z') + struct.pack('>QQ', 0x8000000000000000+len(prefix), 0)
        raw = prefix+known+full('FAttributes', encode_attrs([Field('audioComponent', 2, 7, state)]))
        archive = Archive(raw, 0, len(raw))
        self.assertNotIn('VendorPrivateClass', [v[0] for v in archive.classes.values()])
        pad = archive.root.get('Pad')
        pad.raw_replace(pad.data_start, pad.end, b'x'*101)
        output = archive.serialize(True, canonical_classes=True)
        check = Archive(output, 0, len(output)); node = check.root.get('FAttributes')
        fields, end = read_attrs(output, node.data_start, node.end)
        self.assertEqual(end, node.end)
        self.assertEqual(fields[0].value, state)

    def test_cloned_types_register_once_and_keep_all_objects(self):
        base = declaration('Base')
        child = full('Child', b'abc')
        first = full('Container', base+child)
        archive = Archive(first, 0, len(first))
        source = archive.root.get('Container')
        archive.root.parts = [source.clone(f'track{i}') for i in range(3)]
        invalid = archive.serialize(True)
        with self.assertRaisesRegex(ValueError, 'Duplicate archive class'):
            Archive(invalid, 0, len(invalid)).validate_class_registry()
        output = archive.serialize(True, canonical_classes=True)
        check = Archive(output, 0, len(output))
        self.assertEqual(check.validate_class_registry(), 3)
        self.assertEqual(sum(n.name == 'Container' for n in check.root.walk()), 3)
        children = [n for n in check.root.walk() if n.name == 'Child']
        self.assertEqual(len(children), 3)
        self.assertTrue(all(output[n.data_start:n.end] == b'abc' for n in children))
        for node in children[1:]:
            self.assertEqual(struct.unpack_from('>Q', output, node.start)[0],
                             0x8000000000000000+children[0].start)
        self.assertEqual(check.serialize(True), output)
        self.assertEqual(check.serialize(True, canonical_classes=True), output)

    def test_existing_references_use_canonical_definition_after_cloning(self):
        prefix = full('Pad', b'x')
        leaf = full('Leaf', b'abc')
        source = prefix+leaf+struct.pack('>QQ', 0x8000000000000000+len(prefix), 2)+b'yz'
        archive = Archive(source, 0, len(source))
        nodes = [n for n in archive.root.parts if n.name == 'Leaf']
        archive.root.parts = [archive.root.get('Pad')]+[n.clone(f'track{i}') for i in range(3) for n in nodes]
        output = archive.serialize(True, canonical_classes=True)
        check = Archive(output, 0, len(output))
        leaves = [n for n in check.root.walk() if n.name == 'Leaf']
        self.assertEqual(check.validate_class_registry(), 2)
        self.assertEqual([output[n.data_start:n.end] for n in leaves], [b'abc',b'yz']*3)

    def test_conflicting_versions_and_missing_relocation_are_rejected(self):
        raw = declaration('Base', 0)+declaration('Base', 1)+full('Object', b'x')
        archive = Archive(raw, 0, len(raw))
        with self.assertRaisesRegex(ValueError, 'Conflicting archive class versions'):
            archive.serialize(True, canonical_classes=True)
        with self.assertRaisesRegex(ValueError, 'requires relocation'):
            archive.serialize(canonical_classes=True)


if __name__ == '__main__':
    unittest.main()

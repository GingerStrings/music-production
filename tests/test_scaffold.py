"""Identity and routing invariants for cloned tracks, using synthetic fields."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cpr_fields import Field,walk,encode_attrs,read_attrs
from cpr_scaffold import remap_identities,remap_plugin_path

class ScaffoldIdentityTests(unittest.TestCase):
    def source(self):
        ident=(123).to_bytes(8,'big')
        return [Field('Owned',2,20,(b'Example\0',ident,[Field('RuntimeID',1,0,9)])),
            Field('Alias',2,21,ident),Field('Bus UID',1,0,37),
            Field('Internal',2,6,[Field('InputBusValue',2,6,[Field('Value',1,0,37)])]),
            Field('External',2,6,[Field('OutputBusValue',2,6,[Field('Value',1,0,6)])]),
            Field('Unrelated',2,6,[Field('Value',1,0,37)]),
            Field('State',2,7,b'\0\xff opaque state')]

    def test_clones_separate_ids_preserve_aliases_and_internal_routes(self):
        source=self.source();before=encode_attrs(source)
        clones=[]
        for index in range(3):
            attrs=copy.deepcopy(source);remap_identities(attrs,index)
            d=dict(walk(attrs))
            self.assertEqual(d[('Alias',)].value,d[('Owned',)].value[1])
            self.assertEqual(d[('Internal','InputBusValue','Value')].value,d[('Bus UID',)].value)
            self.assertEqual(d[('External','OutputBusValue','Value')].value,6)
            self.assertEqual(d[('Unrelated','Value')].value,37)
            self.assertEqual(d[('State',)].value,b'\0\xff opaque state')
            clones.append((d[('Alias',)].value,d[('Owned','RuntimeID')].value,d[('Bus UID',)].value))
            encoded=encode_attrs(attrs);decoded,end=read_attrs(encoded,0,len(encoded))
            self.assertEqual(end,len(encoded));self.assertEqual(encode_attrs(decoded),encoded)
        for column in zip(*clones):self.assertEqual(len(set(column)),3)
        self.assertEqual(encode_attrs(source),before)

    def test_external_object_alias_is_rejected(self):
        attrs=self.source();attrs[1].value=(999).to_bytes(8,'big')
        with self.assertRaisesRegex(ValueError,'external object'):remap_identities(attrs,0)

    def test_plugin_instance_remapping_does_not_rematch_new_or_prefix_ids(self):
        self.assertEqual(remap_plugin_path(b'Slot\\BASE-0\0',{'BASE-0','DONOR-1'},'DONOR-15'),b'Slot\\DONOR-15\0')
        self.assertEqual(remap_plugin_path(b'Slot\\DONOR-10\0',{'BASE-0','DONOR-1'},'DONOR-15'),b'Slot\\DONOR-10\0')
        self.assertEqual(remap_plugin_path(b'Slot\\DONOR-1\\Param\0',{'BASE-0','DONOR-1'},'DONOR-15'),b'Slot\\DONOR-15\\Param\0')

if __name__=='__main__':unittest.main()

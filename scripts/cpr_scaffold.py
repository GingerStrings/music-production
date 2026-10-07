#!/usr/bin/env python3
"""Clone an observed instrument-track scaffold and populate a native CPR.

The input template must contain an I/O folder and a first instrument track with
one MIDI part. Donor plugin attributes are copied from explicitly named saved
projects. No plugin or DAW is started. See references/cpr-scaffold.md.
"""
import argparse
import copy
import math
import re
from pathlib import Path
import struct
import sys
from cpr_archive import Archive, Node, Raw, riff_chunks
from cpr_fields import read_attrs, encode_attrs, pack_string, walk, text_value
from cpr_midi import parse_midi, encode_event, compare_events, PPQ
from cpr_timeline import read_tempo, read_meter, write_tempo, write_meter
from cubase_project import Project, root_archives, read_archive, exactly, digest, LIMIT
from music_data import load_json, save_json, new_file, validate_performance


def string(value):
    return value.encode('utf-8')+b'\0\xef\xbb\xbf'


def remap_plugin_path(value,previous_ids,new_id):
    """Replace instance tokens once; UID-1 must not match UID-10."""
    options=sorted({p.encode('utf-8') for p in previous_ids},key=len,reverse=True)
    pattern=b'(?:'+b'|'.join(re.escape(p) for p in options)+rb')(?![0-9])'
    return re.sub(pattern,lambda _:new_id.encode('utf-8'),value)


def field(attrs,*path):
    return dict(walk(attrs))[path]


def instrument_attributes(data,node):
    start=node.data_start+29
    attrs,end=read_attrs(data,start,node.end)
    if encode_attrs(attrs)!=data[start:end]:raise ValueError('Instrument attributes failed lossless round trip')
    field(attrs,'Name','String');field(attrs,'Synth Slot','Plugin','audioComponent')
    return attrs,start,end


def load_donor(path,index,expected_hash=None,cache=None):
    if cache is None:cache={}
    cache_key=(str(Path(path).resolve()),expected_hash)
    if cache_key in cache:
        data,a,tracks=cache[cache_key]
    else:
        data,a,tracks=read_donor(path,expected_hash)
        cache[cache_key]=(data,a,tracks)
    if type(index) is not int or not 1<=index<=len(tracks):raise ValueError('Invalid donor track index')
    attrs,_,_=instrument_attributes(data,exactly(tracks[index-1].walk(),'MInstrumentTrack'))
    plugin=copy.deepcopy(field(attrs,'Synth Slot','Plugin').value)
    return plugin,dict(source=str(Path(path).resolve()),source_sha256=digest(data),source_track=index,
                       source_name=text_value(field(attrs,'Name','String')))


def read_donor(path,expected_hash=None):
    data=Path(path).read_bytes()
    if len(data)>LIMIT:raise ValueError('Donor exceeds size limit')
    if expected_hash is not None and digest(data)!=expected_hash:raise ValueError('Donor fingerprint mismatch')
    chunks=riff_chunks(data);roots=root_archives(data,chunks)
    a=read_archive(data,chunks,roots['Arrangement1'])
    tracks=[n for n in a.root.walk() if n.name=='MInstrumentTrackEvent']
    return data,a,tracks


def remap_identities(attrs,index):
    """Preserve aliases while separating cloned object, runtime and bus IDs."""
    fields=list(walk(attrs));ids={};runtimes={};buses={}
    for path,f in fields:
        values=([f.value] if f.sub==20 else f.value if f.sub==201 else []) if f.typ==2 else []
        for _,ident,_ in values:
            ids.setdefault(ident,(0x4000000000000000+(index+1)*0x100000+len(ids)).to_bytes(8,'big'))
        if f.name=='RuntimeID' and f.typ==1:runtimes.setdefault(f.value,1_000_000+(index+1)*10000+len(runtimes))
        if f.name=='Bus UID' and f.typ==1:buses.setdefault(f.value,10000+(index+1)*100+len(buses))
    for path,f in fields:
        if f.typ==2 and f.sub==20:
            cls,ident,group=f.value;f.value=(cls,ids[ident],group)
        elif f.typ==2 and f.sub==201:f.value=[(cls,ids[ident],group) for cls,ident,group in f.value]
        elif f.typ==2 and f.sub==21:
            if f.value not in ids:raise ValueError('Cloned attributes reference an external object identity')
            f.value=ids[f.value]
        if f.name=='RuntimeID' and f.typ==1:f.value=runtimes[f.value]
        if f.name=='Bus UID' and f.typ==1:f.value=buses[f.value]
        if f.typ==1 and f.name=='Value' and len(path)>1 and path[-2] in ('InputBusValue','OutputBusValue') and f.value in buses:
            f.value=buses[f.value]
    return dict(object_ids=len(ids),runtime_ids=len(runtimes),bus_ids=len(buses))


def rename_list(node,data,name):
    size=struct.unpack_from('>I',data,node.data_start)[0]
    if not 0<size<4096 or node.data_start+4+size>node.end:raise ValueError('Unsupported list name')
    node.raw_replace(node.data_start,node.data_start+4+size,pack_string(string(name)))


def root_id_table(archive):
    root=archive.root.get('MRoot');tail=root.parts[-1]
    if not isinstance(tail,Raw) or tail.origin is None:raise ValueError('Missing root ID table')
    dest={n.data_start-archive.base:n for n in archive.root.walk()}
    count=int.from_bytes(tail.data[:2],'big')
    if not 1<=count<=512 or len(tail.data)!=2+count*10+8 or tail.data[-8:]!=bytes(8):
        raise ValueError('Unsupported root ID table extent')
    rows=[struct.unpack_from('>HQ',tail.data,2+i*10) for i in range(count)]
    if len({i for i,_ in rows})!=count or any(v not in dest for _,v in rows):raise ValueError('Invalid root ID links')
    return root,tail,[(i,dest[v]) for i,v in rows]


def set_transport(data,chunks,index,seconds):
    a=read_archive(data,chunks,index);node=exactly(a.root.walk(),'FAttributes')
    attrs,end=read_attrs(data,node.data_start,node.end)
    if end!=node.end:raise ValueError('Unexpected transport attributes')
    for name in ('Time','Time2','Cycle Left','Cycle Right','Punch Left','Punch Right'):
        if field(attrs,'Transport',name,'Domain','Type').value!=1 or field(attrs,'Transport',name,'Domain','Period').value!=1:
            raise ValueError('Unsupported transport time domain')
        field(attrs,'Transport',name,'Time').value=seconds if name.endswith('Right') else 0.
    encoded=encode_attrs(attrs)
    if len(encoded)!=node.end-node.data_start:raise ValueError('Unexpected transport size change')
    output=bytearray(data[a.start:a.end]);s=node.data_start-a.start
    output[s:s+len(encoded)]=encoded
    return bytes(output)


def assemble(data,performance,mapping):
    if len(data)>LIMIT:raise ValueError('Template exceeds size limit')
    p=validate_performance(performance)
    if p['schema_version']!=2:raise ValueError('Scaffold builder requires performance v2')
    if set(mapping)!={'template_sha256','output_bus_uid','instruments'}:raise ValueError('Invalid scaffold mapping keys')
    if mapping['template_sha256']!=digest(data):raise ValueError('Template fingerprint mismatch')
    if type(mapping['output_bus_uid']) is not int or mapping['output_bus_uid']<=0:raise ValueError('Invalid output bus UID')
    if len(mapping['instruments'])!=len(p['tracks']):raise ValueError('Every performance track needs one instrument mapping')
    if [t['template_index'] for t in p['tracks']]!=list(range(1,len(p['tracks'])+1)):
        raise ValueError('Scaffold track indices must be consecutive in output order')
    chunks=riff_chunks(data);roots=root_archives(data,chunks)
    a=read_archive(data,chunks,roots['Arrangement1'])
    a.validate_class_registry()
    tl=a.root.get('MTrackList');direct=[x for x in tl.parts if isinstance(x,Node)]
    if not direct or direct[0].name!='MFolderTrack':raise ValueError('Expected an initial I/O folder')
    io=direct[0]
    if any(n.name in ('MInstrumentTrackEvent','MMidiTrackEvent','MAudioTrackEvent') for n in io.walk()):
        raise ValueError('Initial folder contains musical tracks')
    exactly(io.walk(),'MTempoTrackEvent');exactly(io.walk(),'MSignatureTrackEvent')
    source=next(n for n in a.root.walk() if n.name=='MInstrumentTrackEvent')
    part=exactly(source.walk(),'MMidiPart');placement=exactly(source.walk(),'MMidiPartEvent')
    source_ins=exactly(source.walk(),'MInstrumentTrack');source_attrs,attrs_start,attrs_end=instrument_attributes(data,source_ins)
    source_plugin_id=text_value(field(source_attrs,'Synth Slot','Plugin','IDString'))
    # Template music is replaced completely. Its high-resolution velocity values
    # need not equal their rounded MIDI bytes; output verification stays strict.
    count_offset,event_start,_=parse_midi(data,part,strict_values=False)
    for n in source.walk():
        if n.name=='MAutoListNode' and struct.unpack_from('>I',data,n.data_start+24)[0]:
            raise ValueError('Scaffold has active host automation')
    if any(struct.unpack_from('>d',data,n.data_start+2)[0]!=0 for n in (source,placement)):
        raise ValueError('Scaffold track and part must start at zero')
    prefix=tl.parts[0]
    if not isinstance(prefix,Raw) or prefix.origin!=tl.data_start:raise ValueError('Unsupported top-level track list')
    name_length=struct.unpack_from('>I',data,tl.data_start)[0];count_pos=4+name_length+14
    if struct.unpack_from('>I',prefix.data,count_pos)[0]!=len(direct):raise ValueError('Track list count mismatch')
    root,id_raw,id_rows=root_id_table(a)
    # Preserve the I/O subtree and replace the musical folders/tracks. Save class
    # declarations immediately before the first instrument with their provenance.
    preceding=None
    for parent in a.root.walk():
        for i,child in enumerate(parent.parts):
            if child is source and i and isinstance(parent.parts[i-1],Raw):preceding=parent.parts[i-1]
    if preceding is None or len(preceding.data)>1024:raise ValueError('Missing bounded instrument class preamble')
    tracks=[];reports=[];donor_cache={};archive_cache={}
    for index,(music,spec) in enumerate(zip(p['tracks'],mapping['instruments'])):
        allowed={'source_project','source_track','source_sha256','component_file','controller_file','name','gain_db'}
        if set(spec)-allowed:raise ValueError('Unknown instrument mapping field')
        key=(spec['source_project'],spec['source_track'],spec.get('source_sha256'))
        if key not in donor_cache:donor_cache[key]=load_donor(*key,cache=archive_cache)
        plugin,donor_report=copy.deepcopy(donor_cache[key])
        if spec.get('component_file'):field(plugin,'audioComponent').value=Path(spec['component_file']).read_bytes()
        if spec.get('controller_file'):field(plugin,'editController').value=Path(spec['controller_file']).read_bytes()
        comp_hash=digest(field(plugin,'audioComponent').value)
        controller=next((f for f in plugin if f.name=='editController'),None)
        controller_hash=digest(controller.value) if controller else None
        uid=text_value(field(plugin,'Plugin UID','GUID'));old_id=text_value(field(plugin,'IDString'))
        ident=f'{uid}-{index}'
        field(plugin,'IDString').value=ident.encode()+b'\0'
        name=music.get('name',spec.get('name',f'Track {index+1}'))
        field(plugin,'Plugin Name').value=string(name)
        attrs=copy.deepcopy(source_attrs)
        # Clear base-instrument quick controls, whose parameter meanings do not
        # transfer to another preset. Plugin-owned controls travel with the donor.
        qc=field(attrs,'Quick Controls','QCDestinations')
        if qc.sub!=20:raise ValueError('Unsupported quick control object')
        field(qc.value[2],'obj').value=[]
        field(attrs,'Synth Slot','Plugin').value=plugin
        identities=remap_identities(attrs,index)
        for path,f in walk(attrs):
            if f.typ==8 and f.name=='NodePath':
                f.value=remap_plugin_path(f.value,{old_id,source_plugin_id},ident)
            if f.typ==1 and f.name in ('Bypass Inserts','Bypass Sends'):f.value=1
            if f.typ==1 and f.name=='Bypass' and any(x in ('StripFolder','EQ') for x in path):f.value=1
        field(attrs,'Midi Channel','Pan','Value').value=0
        outputs=field(attrs,'Synth Slot','Output Channels')
        if outputs.sub!=5 or not outputs.value or not outputs.value[0] or any(outputs.value[1:]):
            raise ValueError('Scaffold needs one active stereo instrument output')
        channel=next(f for f in outputs.value[0] if f.name=='Output Channel').value
        # Only exact saved fader anchors are supported here; this is not a new
        # model for Cubase's nonlinear fader law.
        gains={0:(25856.,0.),-6:(18705.01953125,-6.00000152),-12:(13245.7890625,-11.99999922),-15:(11144.94238281,-15.00000008)}
        db=spec.get('gain_db',-12)
        if db not in gains:raise ValueError('Gain must use a supported saved anchor: 0, -6, -12, -15 dB')
        for group in (attrs,channel):
            field(group,'Name','String').value=string(name)
            field(group,'OutputBusValue','Value').value=mapping['output_bus_uid']
            field(group,'Volume','Value').value=gains[db][0]
            field(group,'Volume','AnchorValue').value=gains[db][1]
            pan=field(group,'Panner','audioComponent')
            if len(pan.value)<8:raise ValueError('Unsupported stereo panner state')
            pan.value=struct.pack('<ff',.5,.5)+pan.value[8:]
        scope=f'track{index}';track=source.clone(scope)
        for target in (track,track.get('MMidiPartEvent')):
            target.raw_replace(target.data_start+10,target.data_start+18,struct.pack('>d',p['end_beats']*PPQ))
        rename_list(track.get('MListNode'),data,name)
        midi=track.get('MMidiPart');rename_list(midi,data,name)
        flag=b'\0' if count_offset+4==part.end else b''
        midi.raw_replace(event_start,midi.end,flag+b''.join(encode_event(e) for e in music['events']))
        midi.raw_replace(count_offset,count_offset+4,struct.pack('>I',len(music['events'])))
        ins=track.get('MInstrumentTrack')
        ins.parts=[Raw(data[ins.data_start:attrs_start],ins.data_start,scope),Raw(encode_attrs(attrs),None,scope),
                   Raw(data[attrs_end:ins.end],attrs_end,scope)]
        tracks.append(track)
        reports.append(dict(index=index+1,name=name,plugin_uid=uid,component_sha256=comp_hash,
            controller_sha256=controller_hash,donor=donor_report,identities=identities,gain_db=db))
    pre=bytearray(prefix.data[:count_pos+4]);struct.pack_into('>I',pre,count_pos,len(tracks)+1)
    tl.parts=[Raw(bytes(pre),None),Raw(prefix.data[count_pos+4:],prefix.origin+count_pos+4),io,
              Raw(preceding.data,preceding.origin)]+tracks
    retained={(n.scope,n.data_start) for n in a.root.walk()}
    old_links=[(i,n) for i,n in id_rows if (n.scope,n.data_start) in retained]
    next_id=max(i for i,_ in id_rows)+1
    links=old_links+[(next_id+i,n) for i,n in enumerate(tracks)]
    id_raw.data=struct.pack('>H',len(links))+bytes(len(links)*10)+bytes(8);id_raw.origin=None
    timeline=write_tempo(data,a.root.get('MTempoTrackEvent'),p['tempo_map'])
    write_meter(data,a.root.get('MSignatureTrackEvent'),p['meter_map'])
    a.serialize(True,canonical_classes=True)
    id_raw.data=struct.pack('>H',len(links))+b''.join(struct.pack('>HQ',i,a.payloads[(n.scope,n.data_start)]-8) for i,n in links)+bytes(8)
    main=a.serialize(True,canonical_classes=True);seconds=timeline.beat_to_seconds(p['end_beats'])
    devices=set_transport(data,chunks,roots['Devices'],seconds)
    body=b''.join(tag+struct.pack('>Q',len(payload))+payload for i,(tag,_,s,e) in enumerate(chunks)
                 for payload in [main if i==roots['Arrangement1'] else devices if i==roots['Devices'] else data[s:e]])
    output=b'RIF2'+struct.pack('>Q',len(body))+b'NUND'+body
    check=Project(output)
    class_count=check.archive.validate_class_registry()
    if len(check.tracks)!=len(tracks):raise ValueError('Cloned track count differs')
    if check.meter_map!=p['meter_map'] or check.tempo_mode['fixed_tempo'] or len(check.tempo_map)!=len(timeline.points):
        raise ValueError('Timeline readback failed')
    for expected,actual in zip(timeline.points,check.tempo_map):
        if expected!=actual:raise ValueError('Tempo readback differs')
    for music,info,expected,actual in zip(p['tracks'],check.info,reports,check.events):
        compare_events(actual,music['events'])
        for key in ('name','plugin_uid','component_sha256','controller_sha256'):
            if info[key]!=expected[key]:raise ValueError(f'Instrument readback mismatch: {key}')
        if info['midi_inserts_bypassed']!=1 or info['host_automation_points']:
            raise ValueError('Unexpected inherited MIDI/automation processing')
        if abs(info['part_beats']-p['end_beats'])>1e-8:raise ValueError('Part extent mismatch')
    _,_,verified_links=root_id_table(check.archive)
    if len(verified_links)!=len(links):raise ValueError('Root ID table count differs')
    if abs(check.transport_fields[('Transport','Cycle Right','Time')].value-seconds)>1e-8:raise ValueError('Locator mismatch')
    report=dict(adapter='observed-rif2-instrument-scaffold-v3',template_sha256=digest(data),output_sha256=digest(output),
        archive_class_count=class_count,duplicate_class_declarations_removed=a.canonicalized_class_count,
        tracks=reports,tempo_map=check.tempo_map,tempo_mode=check.tempo_mode,meter_map=check.meter_map,end_beats=p['end_beats'],seconds=seconds,
        static_validation_passed=True,plugin_executed=False,runtime_tested=False,
        checks=['Archive bounds and byte-identical roundtrip','Unique class declarations and backward class references','Every MIDI event read back','Native tempo cache, all track/point property maps and both meter representations',
                'Plugin component/controller hashes','Track and root-reference counts','Part extents and locator'],
        limitations=['DAW loading, plugin authorization, sample availability and sound are not tested by this static writer.',
                     'Template-level UI settings and opaque nonmusical metadata remain inherited.'])
    return output,report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('template');ap.add_argument('--performance',required=True);ap.add_argument('--mapping',required=True)
    ap.add_argument('--out',required=True);ap.add_argument('--report',required=True)
    args=ap.parse_args()
    paths=[Path(x).resolve() for x in (args.template,args.performance,args.mapping,args.out,args.report)]
    if len(set(paths))!=len(paths):raise ValueError('Template, performance, mapping, CPR and report paths must differ')
    if Path(args.out).suffix.lower()!='.cpr' or Path(args.out).exists() or Path(args.report).exists():raise ValueError('Choose new CPR/report filenames')
    source=Path(args.template).read_bytes()
    output,report=assemble(source,load_json(args.performance),load_json(args.mapping))
    if Path(args.template).read_bytes()!=source:raise ValueError('Source changed during build')
    new_file(args.out,output);save_json(args.report,report)
    print(f'Created {len(report["tracks"])} native instrument tracks; static readback passed.')


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()

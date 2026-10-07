#!/usr/bin/env python3
"""Import SMF into performance v2; optional explicit overflow-bend repair.

Requires mido. Source bytes remain untouched. No clamping, quantization, plugin
loading, or automatic instrument substitution is performed.
"""
import argparse
from collections import defaultdict, deque, Counter
import hashlib
import io
import math
from pathlib import Path
import struct
import sys
from music_data import load_json, save_json, new_file, validate_performance
from music_timeline import TempoMap


def smf_channel_records(data):
    """Read event boundaries even when a pitch bend's data byte is malformed.

    Only channel data bytes are returned. Meta/SysEx payloads are bounded and
    skipped by their declared length; their bytes are never interpreted as MIDI.
    """
    if data[:4]!=b'MThd' or len(data)<14:
        raise ValueError('Expected Standard MIDI File')
    hlen=int.from_bytes(data[4:8],'big')
    if hlen<6 or 8+hlen>len(data):raise ValueError('Invalid SMF header')
    form,tracks,division=struct.unpack_from('>HHH',data,8)
    if form not in (0,1) or not 0<division<0x8000:raise ValueError('Only synchronous PPQ MIDI is supported')
    p=8+hlen;result=[]
    def vlq(pos,end):
        value=0
        for _ in range(4):
            if pos>=end:raise ValueError('Truncated variable-length number')
            byte=data[pos];pos+=1;value=(value<<7)|(byte&127)
            if byte<128:return value,pos
        raise ValueError('Invalid variable-length number')
    for track in range(tracks):
        if p+8>len(data) or data[p:p+4]!=b'MTrk':raise ValueError('Missing MTrk')
        end=p+8+int.from_bytes(data[p+4:p+8],'big');p+=8
        if end>len(data):raise ValueError('Truncated MIDI track')
        tick=0;running=None;port=0;port_declarations=[];track_start=len(result)
        while p<end:
            delta,p=vlq(p,end);tick+=delta
            if p>=end:raise ValueError('Missing MIDI status')
            if data[p]>=128:status=data[p];p+=1
            elif running is not None:status=running
            else:raise ValueError('Missing running status')
            if status==0xff:
                if p>=end:raise ValueError('Truncated meta event')
                typ=data[p];p+=1;n,p=vlq(p,end)
                if p+n>end:raise ValueError('Truncated meta payload')
                if typ==0x21 and n==1:
                    port=data[p];port_declarations.append((tick,port))
                p+=n
            elif status in (0xf0,0xf7):
                n,p=vlq(p,end)
                if p+n>end:raise ValueError('Truncated SysEx')
                p+=n;running=None
            elif 0x80<=status<0xf0:
                running=status;count=1 if status&0xf0 in (0xc0,0xd0) else 2
                if p+count>end:raise ValueError('Truncated channel event')
                raw=list(data[p:p+count])
                result.append(dict(track=track,port=port,tick=tick,status=status,offset=p,data=raw))
                p+=count
            else:raise ValueError('Unsupported SMF system event')
        # Some exporters put the track's only port declaration after setup CCs
        # at tick zero. Treat a single constant initial port as track metadata.
        if port_declarations and all(t==0 for t,_ in port_declarations) and len({v for _,v in port_declarations})==1:
            for r in result[track_start:]:r['port']=port_declarations[0][1]
    if p!=len(data):raise ValueError('Trailing SMF bytes')
    return result


def repair_pitch_overflow(data, enabled=False):
    records=smf_channel_records(data)
    invalid=[r for r in records if any(v>127 for v in r['data'])]
    report=dict(invalid_events=len(invalid),repairs=[])
    if not invalid:return data,report
    if not enabled:raise ValueError(f'{len(invalid)} invalid MIDI events; repair must be explicitly selected')
    if any(r['status']&0xf0!=0xe0 or r['data'][0]>127 for r in invalid):
        raise ValueError('Repair supports only overflow pitch-bend MSB bytes')
    output=bytearray(data)
    affected={(r['track'],r['port'],r['status']&15) for r in invalid}
    for track,port,ch in sorted(affected):
        rr=[r for r in records if (r['track'],r['port'],r['status']&15)==(track,port,ch)]
        rpn=[127,127];ranges=[];cents=0;bends=[];first_bend=None
        for r in rr:
            status=r['status']&0xf0
            if status==0xb0:
                cc,value=r['data']
                if cc==101:rpn[0]=value
                elif cc==100:rpn[1]=value
                elif cc in (98,99):rpn=[127,127]
                elif cc==6 and rpn==[0,0]:ranges.append(r)
                elif cc==38 and rpn==[0,0]:cents=value
                elif cc in (96,97) and rpn==[0,0]:raise ValueError('Incremental pitch-range changes need explicit handling')
                elif cc==121:
                    if ranges or first_bend is not None:raise ValueError('Reset after pitch setup requires explicit handling')
                    rpn=[127,127]
            elif status==0xe0:
                if first_bend is None:first_bend=r['tick']
                bends.append(r)
        if not ranges or any(r['tick']>first_bend for r in ranges) or len({r['data'][1] for r in ranges})!=1 or cents:
            raise ValueError('Repair needs one explicit initial whole-semitone RPN pitch range')
        old=ranges[0]['data'][1]
        if not old:raise ValueError('Cannot repair a zero pitch range')
        values=[r['data'][0]+128*r['data'][1]-8192 for r in bends]
        factor=1
        while any(not -8192<=round(v/factor)<=8191 for v in values):factor*=2
        new=old*factor
        if new>127:raise ValueError('Required pitch range exceeds MIDI RPN limits')
        for r in ranges:output[r['offset']+1]=new
        error=0
        for r,raw in zip(bends,values):
            value=round(raw/factor)
            error=max(error,abs(raw*old-value*new)*100/8192)
            u=value+8192;output[r['offset']]=u&127;output[r['offset']+1]=u>>7
        report['repairs'].append(dict(track=track,port=port,channel=ch,old_range_semitones=old,
            new_range_semitones=new,bends_rescaled=len(bends),max_pitch_error_cents=error,
            malformed_offsets=[r['offset'] for r in invalid if (r['track'],r['port'],r['status']&15)==(track,port,ch)]))
    if any(any(v>127 for v in r['data']) for r in smf_channel_records(output)):
        raise ValueError('Invalid MIDI data remains after repair')
    return bytes(output),report


def import_midi(data, title, groups=None, repair_overflow=False):
    import mido
    repaired,repair=repair_pitch_overflow(data,repair_overflow)
    midi=mido.MidiFile(file=io.BytesIO(repaired),charset='utf-8',clip=False)
    if midi.type not in (0,1):raise ValueError('SMF type 2 is asynchronous')
    ppq=midi.ticks_per_beat;source=[];tempos={};meters={};end=0;extras=[];metadata=[]
    for index,track in enumerate(midi.tracks):
        initial=[];elapsed=0
        for msg in track:
            elapsed+=msg.time
            if msg.type=='midi_port':initial.append((elapsed,msg.port))
        constant_port=initial and all(t==0 for t,_ in initial) and len({v for _,v in initial})==1
        tick=0;port=initial[0][1] if constant_port else 0;notes=defaultdict(deque);events=[];ports=set();order=0
        for msg in track:
            tick+=msg.time;end=max(end,tick);order+=1
            if msg.type=='midi_port':port=msg.port;ports.add(port)
            if msg.is_meta:
                if msg.type=='set_tempo':
                    if tick in tempos and tempos[tick]!=msg.tempo:raise ValueError('Conflicting simultaneous tempi')
                    tempos[tick]=msg.tempo
                elif msg.type=='time_signature':
                    value=(msg.numerator,msg.denominator)
                    if tick in meters and meters[tick]!=value:raise ValueError('Conflicting simultaneous signatures')
                    meters[tick]=value
                elif msg.type not in ('end_of_track','track_name','midi_port'):
                    metadata.append(dict(track=index,tick=tick,event=msg.dict()))
                continue
            base=dict(beat=tick/ppq,channel=getattr(msg,'channel',0))
            if msg.type=='note_on' and msg.velocity:
                event=dict(type='note',**base,pitch=msg.note,velocity=msg.velocity,duration=0)
                notes[(port,msg.channel,msg.note)].append((event,order))
                events.append((tick,order,port,event))
            elif msg.type=='note_off' or msg.type=='note_on' and not msg.velocity:
                queue=notes[(port,msg.channel,msg.note)]
                if not queue:
                    extras.append(dict(track=index,tick=tick,port=port,channel=msg.channel,pitch=msg.note))
                    continue
                event,_=queue.popleft();event['duration']=tick/ppq-event['beat']
                if msg.velocity!=64:event['release_velocity']=msg.velocity
                if event['duration']<0:raise ValueError('Negative source note duration')
            elif msg.type=='control_change':events.append((tick,order,port,dict(type='cc',**base,controller=msg.control,value=msg.value)))
            elif msg.type=='pitchwheel':events.append((tick,order,port,dict(type='pitchbend',**base,value=msg.pitch)))
            elif msg.type=='program_change':events.append((tick,order,port,dict(type='program',**base,program=msg.program)))
            else:raise ValueError(f'Unsupported source event: {msg.type}; source retained')
        if any(queue for queue in notes.values()):raise ValueError(f'Unclosed MIDI note in track {index}')
        active_ports={e[2] for e in events}
        if len(active_ports)>1:raise ValueError('A source track changes active MIDI ports; split it before importing')
        source.append(dict(name=track.name or f'Track {index+1}',events=events,port=next(iter(active_ports),0)))
    tempos.setdefault(0,500000);meters.setdefault(0,(4,4))
    if groups is None:groups=[dict(name=t['name'],source_tracks=[i]) for i,t in enumerate(source) if t['events']]
    used=set();tracks=[]
    for index,g in enumerate(groups,1):
        if set(g)!={'name','source_tracks'} or not g['source_tracks']:raise ValueError('Invalid MIDI track grouping')
        joined=[];channels={}
        for i in g['source_tracks']:
            if type(i) is not int or not 0<=i<len(source) or i in used:raise ValueError('Invalid/duplicate source track group')
            used.add(i);t=source[i]
            for tick,order,port,event in t['events']:
                ch=event['channel']
                if ch in channels and channels[ch]!=port:raise ValueError('Grouping merges different MIDI ports on one channel')
                channels[ch]=port;joined.append((tick,i,order,event))
        joined.sort(key=lambda e:e[:3])
        tracks.append(dict(template_index=index,name=g['name'],source_tracks=g['source_tracks'],events=[e[3] for e in joined]))
    missing=[i for i,t in enumerate(source) if t['events'] and i not in used]
    if missing:raise ValueError(f'Grouping omitted nonempty source tracks: {missing}')
    tempo_map=[dict(beat=t/ppq,bpm=60_000_000/v,curve='step') for t,v in sorted(tempos.items())]
    meter_map=[dict(beat=t/ppq,numerator=n,denominator=d) for t,(n,d) in sorted(meters.items())]
    report=dict(source_sha256=hashlib.sha256(data).hexdigest(),repaired_sha256=hashlib.sha256(repaired).hexdigest(),
        source_ppq=ppq,source_tracks=len(source),source_ports=[t['port'] for t in source],pitch_repair=repair,
        unpaired_note_offs=extras,metadata_outside_performance=metadata,
        seconds=TempoMap(tempo_map).beat_to_seconds(end/ppq),
        counts=dict(Counter(e['type'] for t in tracks for e in t['events'])))
    report['initial_port_policy']='A sole constant tick-zero port declaration applies to the whole track, including preceding tick-zero setup events.'
    report['zero_duration_notes']=sum(e['type']=='note' and e['duration']==0 for t in tracks for e in t['events'])
    performance=dict(schema_version=2,kind='performance',title=title,tempo_map=tempo_map,meter_map=meter_map,
        end_beats=end/ppq,tracks=tracks,source_report=report)
    return validate_performance(performance),repaired


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source');p.add_argument('--title',required=True);p.add_argument('--out',required=True)
    p.add_argument('--groups');p.add_argument('--repair-overflow',action='store_true');p.add_argument('--repaired-midi')
    a=p.parse_args()
    paths=[Path(x).resolve() for x in (a.source,a.groups,a.out,a.repaired_midi) if x]
    if len(set(paths))!=len(paths):raise ValueError('Source, groups, performance and repaired MIDI paths must differ')
    if Path(a.out).exists() or a.repaired_midi and Path(a.repaired_midi).exists():raise ValueError('Choose new output filenames')
    data=Path(a.source).read_bytes()
    performance,repaired=import_midi(data,a.title,load_json(a.groups) if a.groups else None,a.repair_overflow)
    save_json(a.out,performance)
    if a.repaired_midi:new_file(a.repaired_midi,repaired)
    print(f'Imported {len(performance["tracks"])} tracks; {performance["source_report"]["counts"]}')


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()

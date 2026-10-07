"""Observed CPR tempo/meter tables; no absolute file offsets or vendor assets."""
import copy
import math
import struct
from cpr_fields import Reader, read_attrs, encode_attrs, walk
from cpr_archive import Raw
from music_timeline import TempoMap, validate_meters

PPQ = 480


def _property_map_end(data, start, end, nodes):
    """Bound the observed fourcc property encoding without rewriting its bytes."""
    reader = Reader(data, start, end)
    for _ in range(reader.count()):
        tag = reader.take(4)
        typ = reader.number('H') & 0xff
        if typ in (1, 4):
            reader.take(8)
        elif typ == 8:
            reader.string()
        elif typ & 15 == 2:
            # A property object may be preceded by base-class declarations.
            while data[reader.pos:reader.pos+8] == b'\xff'*7+b'\xfe':
                reader.take(8)
                label = reader.string()
                if not label.endswith(b'\0'):
                    raise ValueError('Invalid property class declaration')
                reader.take(2)
            child = nodes.get(reader.pos)
            if child is not None:
                reader.take(child.end-reader.pos)
            elif data[reader.pos:reader.pos+8] == bytes(8):
                reader.take(8)
            else:
                raise ValueError(f'Unsupported property object: {tag!r}')
        else:
            raise ValueError(f'Unsupported property type: {typ:#x}')
    return reader.pos


def tempo_properties(data, node, tail, count):
    """Return track/point map spans and require consumption of the entire node.

    Version 3 stores one track map followed by a map for EACH tempo point.
    Even an empty point map occupies four bytes. Version 2 has only the track
    map. Unknown versions are rejected instead of guessing their trailer.
    """
    if node.class_version not in (2, 3):
        raise ValueError(f'Unsupported native tempo class version: {node.class_version}')
    nodes = {n.start: n for n in node.walk() if n is not node}
    start = tail+6
    try:
        pos = _property_map_end(data, start, node.end, nodes)
    except ValueError as error:
        raise ValueError(f'Invalid tempo track properties: {error}') from error
    track = (start, pos)
    points = []
    if node.class_version == 3:
        for i in range(count):
            start = pos
            try:
                pos = _property_map_end(data, start, node.end, nodes)
            except ValueError as error:
                raise ValueError(f'Invalid tempo point {i+1} properties: {error}') from error
            points.append((start, pos))
    if pos != node.end:
        raise ValueError('Unexpected bytes after native tempo properties')
    return track, points


def read_tempo(data, node):
    start = node.data_start
    if start+4 > node.end:
        raise ValueError('Truncated native tempo table')
    count = struct.unpack_from('>I', data, start)[0]
    tail = start+4+22*count
    if not 1 <= count <= 100_000 or tail+6 > node.end:
        raise ValueError('Invalid native tempo table')
    points, cached = [], []
    for i in range(count):
        spb, seconds, ticks, shape = struct.unpack_from('>fddH', data, start+4+22*i)
        if not math.isfinite(spb) or spb <= 0 or shape not in (0,1):
            raise ValueError('Invalid native tempo point')
        points.append(dict(beat=ticks/PPQ, bpm=60/spb, curve='linear' if shape else 'step'))
        cached.append(seconds)
    timeline = TempoMap(points)
    # Saved Cubase files cache time using higher precision than their float32 SPB.
    if any(not math.isfinite(a) or abs(a-b)>max(1e-4, abs(b)*2e-7) for a,b in zip(cached,timeline.seconds)):
        raise ValueError('Native tempo time cache disagrees with tempo integration')
    fallback, mode = struct.unpack_from('>fH', data, tail)
    if not 1 <= fallback <= 1000 or mode not in (0,1):
        raise ValueError('Unsupported native tempo mode')
    _, properties = tempo_properties(data, node, tail, count)
    return points, tail, dict(fallback_bpm=fallback, fixed_tempo=bool(mode),
                             class_version=node.class_version,
                             point_property_maps=len(properties))


def write_tempo(data, node, points):
    old_points, tail, _ = read_tempo(data, node)
    _, properties = tempo_properties(data, node, tail, len(old_points))
    requested = TempoMap(points)
    empty_properties = all(data[s:e] == bytes(4) for s,e in properties)
    if properties and not empty_properties:
        # Preserve opaque per-point metadata and its archive references in place.
        # A changed set of positions needs an explicit metadata ownership policy.
        if [p['beat'] for p in old_points] != [p['beat'] for p in requested.points]:
            raise ValueError('Cannot add, remove or move tempo points with nonempty point properties')
    quantized = [dict(p,bpm=60/struct.unpack('>f',struct.pack('>f',60/p['bpm']))[0]) for p in requested.points]
    timeline = TempoMap(quantized)
    table = struct.pack('>I',len(points)) + b''.join(
        struct.pack('>fddH',60/p['bpm'],t,p['beat']*PPQ,int(p['curve']=='linear'))
        for p,t in zip(quantized,timeline.seconds))
    table += struct.pack('>fH',points[0]['bpm'],0)
    node.raw_replace(node.data_start,tail+6,table)
    if properties and empty_properties:
        node.raw_replace(properties[0][0],properties[-1][1],bytes(4*len(points)))
    return timeline


def read_meter(data, node):
    s=node.data_start
    count=struct.unpack_from('>I',data,s)[0]
    tail=s+4+16*count
    if not 1<=count<=100_000 or tail>node.end:
        raise ValueError('Invalid native meter table')
    points=[]
    for i in range(count):
        ticks,n,d,flags=struct.unpack_from('>iHHQ',data,s+4+16*i)
        points.append(dict(beat=ticks/PPQ,numerator=n,denominator=d))
    bars=validate_meters(points)
    attrs_nodes=[n for n in node.walk() if n.name=='FAttributes']
    if len(attrs_nodes)!=1:
        raise ValueError('Expected one native SignatureEvent attributes table')
    an=attrs_nodes[0]
    attrs,end=read_attrs(data,an.data_start,an.end)
    if end!=an.end or encode_attrs(attrs)!=data[an.data_start:an.end]:
        raise ValueError('Signature attributes round trip failed')
    table=next((f for f in attrs if f.name=='SignatureEvent'),None)
    if table is None or (table.typ,table.sub)!=(2,201) or len(table.value)!=count:
        raise ValueError('Unsupported SignatureEvent object array')
    for p,(_,_,group) in zip(bars,table.value):
        fields=dict(walk(group))
        for key,expected in [('Start',float(p['bar'])),('Bar',p['bar']),('Numerator',p['numerator']),
                             ('Denominator',p['denominator']),('Position',round(p['beat']*PPQ))]:
            if (key,) not in fields or fields[(key,)].value!=expected:
                raise ValueError(f'Meter table/attributes mismatch: {key}')
    return points,tail,an,attrs,table


def write_meter(data,node,points):
    _,tail,an,attrs,table=read_meter(data,node)
    bars=validate_meters(points)
    if any(abs(p['beat']*PPQ-round(p['beat']*PPQ))>1e-8 or p['beat']*PPQ>0x7fffffff for p in bars):
        raise ValueError('Native signatures require integer 480-PPQ positions')
    original=table.value[0]
    group_fields=dict(walk(original[2]))
    if any(f.name=='Additional Attributes' for f in original[2]):
        raise ValueError('Template has custom click accents; use an uncustomized signature template')
    ids=set()
    # IDs are object identities, not archive offsets. Derive from the existing ID
    # and check the entire source for collisions, retaining the first object ID.
    base=int.from_bytes(original[1],'big')
    objects=[]
    for i,p in enumerate(bars):
        cls,ident,group=copy.deepcopy(original)
        ident=(base+i*0x100000000).to_bytes(8,'big')
        if i and ident in data:
            raise ValueError('Generated signature object ID collides with source')
        if ident in ids:raise ValueError('Duplicate signature ID')
        ids.add(ident)
        fields=dict(walk(group))
        for key,value in [('Start',float(p['bar'])),('Bar',p['bar']),('Numerator',p['numerator']),
                          ('Denominator',p['denominator']),('Position',round(p['beat']*PPQ))]:
            fields[(key,)].value=value
        if ('Flags',) in fields:fields[('Flags',)].value=8 if i==0 else 0
        objects.append((cls,ident,group))
    table.value=objects
    # Compact flags are retained only for the initial signature; remaining events
    # use the unselected, default-accent form seen in saved multi-meter projects.
    first_flags=struct.unpack_from('>Q',data,node.data_start+12)[0]
    raw=struct.pack('>I',len(bars))+b''.join(struct.pack('>iHHQ',round(p['beat']*PPQ),
        p['numerator'],p['denominator'],first_flags if i==0 else 0) for i,p in enumerate(bars))
    node.raw_replace(node.data_start,tail,raw)
    an.parts=[Raw(encode_attrs(attrs),None,an.scope)]

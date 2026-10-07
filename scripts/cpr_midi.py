"""Codec for observed native Cubase MIDI records (480 ticks/quarter).

Pitch bend uses MIDI LSB/MSB and a GLFX attribute. See cpr-format.md for
independent saved-project evidence and the remaining host-validation boundary.
"""
import math
import struct

PPQ = 480


def parse_midi(data, node, strict_values=True):
    p = node.data_start
    if p + 4 > node.end:
        raise ValueError("Truncated MIDI part")
    length = struct.unpack_from('>I', data, p)[0]
    if not 0 < length < 4096:
        raise ValueError("Unsupported MIDI part name")
    count_offset = p + 4 + length + 20
    if count_offset + 4 > node.end:
        raise ValueError("Truncated MIDI list header")
    count = struct.unpack_from('>I', data, count_offset)[0]
    if count > 200_000:
        raise ValueError("Excessive MIDI event count")
    if count == 0 and count_offset + 4 == node.end:
        return count_offset, node.end, []
    if count_offset + 5 > node.end:
        raise ValueError("Truncated MIDI declaration flag")
    p = count_offset + 5
    flag = data[count_offset + 4]
    if flag:
        declarations = [x for x in node.walk() if x.name == 'MMidiSysex' and x.end == x.data_start]
        if len(declarations) != 1 or not p <= declarations[0].start < p + 2048:
            raise ValueError("Unsupported MIDI declaration layout")
        p = declarations[0].end
    event_start, events = p, []
    for _ in range(count):
        if p + 18 > node.end:
            raise ValueError("Truncated MIDI event header")
        status, ticks, channel, key, value, flags, attr_count = struct.unpack_from('>BdBBBHI', data, p)
        p += 18
        if status not in (0x90, 0xB0, 0xC0, 0xE0) or not math.isfinite(ticks) or ticks < 0:
            raise ValueError("Unsupported MIDI event")
        if not 0 <= channel < 16 or not 0 <= key < 128 or not 0 <= value < 128 or attr_count > 32:
            raise ValueError("Invalid MIDI data")
        attrs = {}
        for _ in range(attr_count):
            if p + 14 > node.end:
                raise ValueError("Truncated MIDI attribute")
            name, typ = struct.unpack_from('>4sH', data, p)
            if typ not in (1, 4) or name in attrs:
                raise ValueError("Unsupported MIDI attribute")
            attrs[name] = struct.unpack_from('>q' if typ == 1 else '>d', data, p + 6)[0]
            p += 14
        event = dict(type={0x90:'note', 0xB0:'cc', 0xC0:'program', 0xE0:'pitchbend'}[status], beat=ticks/PPQ, channel=channel)
        if status == 0x90:
            if p + 25 > node.end:
                raise ValueError("Truncated note duration")
            duration = struct.unpack_from('>d', data, p)[0] / PPQ
            if not math.isfinite(duration) or duration < 0 or value == 0:
                raise ValueError("Invalid note duration or velocity")
            event.update(pitch=key, velocity=value, duration=duration)
            release_velocity=data[p+24]
            if release_velocity>127:raise ValueError('Invalid note release velocity')
            if release_velocity!=64:event['release_velocity']=release_velocity
            p += 25
        elif status == 0xB0:
            event.update(controller=key, value=value)
        elif status == 0xC0:
            if value != 0:
                raise ValueError('Unsupported program-change secondary byte')
            event.update(program=key)
        else:
            event.update(value=(value << 7 | key)-8192)
        if status == 0xE0 and b'TDRH' in attrs:
            raise ValueError('Unverified high-resolution pitch-bend attribute')
        if strict_values and status != 0xE0 and b'TDRH' in attrs and not math.isclose(attrs[b'TDRH'], value/127, abs_tol=1e-14):
            raise ValueError("Inconsistent native MIDI value")
        events.append(event)
    if p != node.end:
        raise ValueError("Unparsed MIDI payload remains")
    if any(a['beat'] > b['beat'] for a, b in zip(events, events[1:])):
        raise ValueError("Unsorted MIDI records")
    return count_offset, event_start, events


def encode_event(e):
    if e['type'] in ('pitchbend', 'program'):
        if e['type'] == 'pitchbend':
            if type(e['value']) is not int or not -8192 <= e['value'] <= 8191:
                raise ValueError('Pitch bend must be a signed 14-bit integer')
            raw=e['value']+8192
            status, key, value = 0xE0, raw & 127, raw >> 7
        else:
            if type(e['program']) is not int or not 0 <= e['program'] <= 127:
                raise ValueError('Program must be in 0..127')
            status, key, value = 0xC0, e['program'], 0
        return (struct.pack('>BdBBBHI', status, e['beat']*PPQ, e['channel'], key, value, 0, 1)
                + b'GLFX' + struct.pack('>Hq', 1, 0))
    if e['type'] not in ('note', 'cc'):
        raise ValueError('Unsupported event type')
    note = e['type'] == 'note'
    value = e['velocity'] if note else e['value']
    key = e['pitch'] if note else e['controller']
    header = struct.pack('>BdBBBHI', 0x90 if note else 0xB0, e['beat']*PPQ,
                         e['channel'], key, value, 0, 5 if note else 2)
    attrs = b'GLFX' + struct.pack('>Hq', 1, 0)
    if note:
        attrs += b'Pler' + struct.pack('>Hd', 4, 0)
    attrs += b'TDRH' + struct.pack('>Hd', 4, value/127)
    if note:
        release=e.get('release_velocity',64)
        attrs += b'VffO' + struct.pack('>Hd', 4, release/127)
        attrs += b'adcn' + struct.pack('>Hq', 1, 0x2000000000)
        attrs += struct.pack('>d', e['duration']*PPQ) + b'\0'*16 + bytes([release])
    return header + attrs


def compare_events(actual, expected):
    if len(actual) != len(expected):
        raise ValueError("MIDI event count differs after writing")
    for i, (a, e) in enumerate(zip(actual, expected)):
        if set(a) != set(e):
            raise ValueError(f"MIDI event {i} fields differ")
        for key in a:
            equal = (math.isclose(a[key], e[key], rel_tol=0, abs_tol=1e-8)
                     if key in ('beat', 'duration') else a[key] == e[key])
            if not equal:
                raise ValueError(f"MIDI event {i} {key} differs after writing")

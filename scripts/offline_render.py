"""Small, explicit primitives for rendering a prepared VST3 instrument.

This module does not load plug-ins, inspect projects, infer routing, install
dependencies, or reset an instrument. Import, state wrapping, MIDI scheduling,
and gain conversion require only Python's standard library. Only the audio
render function imports numpy. The caller owns plug-in initialization, state,
tempo conversion, musical decisions, and an adequate release-tail duration.
"""
from collections.abc import Mapping
import math
import struct
from xml.etree import ElementTree as ET


def _integer(value, name, low, high=None):
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError(f'{name} must be an integer in {low}..{high if high is not None else "unbounded"}')
    return value


def _number(value, name, low=0, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a finite number')
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f'{name} must be a finite number') from exc
    if not math.isfinite(result) or result < low or (high is not None and result > high):
        raise ValueError(f'{name} is outside the supported finite range')
    return result


def _juce_memory_block(data):
    # MemoryBlock.toBase64Encoding uses least-significant bits first and a
    # custom alphabet; standard base64.b64encode produces different data.
    alphabet = b'.ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+'
    encoded = bytearray()
    accumulator, bits = 0, 0
    for byte in data:
        accumulator |= byte << bits
        bits += 8
        while bits >= 6:
            encoded.append(alphabet[accumulator & 63])
            accumulator >>= 6
            bits -= 6
    if bits:
        encoded.append(alphabet[accumulator & 63])
    return f'{len(data)}.' + encoded.decode('ascii')


def make_vst3_raw_state(component: bytes, controller: bytes = b'') -> bytes:
    """Wrap opaque component/controller bytes for JUCE's VST3 state loader.

    Both arguments must be bytes. Child text uses JUCE MemoryBlock encoding,
    including the decimal byte-count prefix. The envelope is ``VC2!``, a
    uint32 little-endian XML byte count, UTF-8 XML, and one zero terminator.
    This constructs an envelope only; it cannot verify a plug-in's payload.
    """
    if not isinstance(component, bytes) or not isinstance(controller, bytes):
        raise TypeError('Component and controller state must be bytes')
    root = ET.Element('VST3PluginState')
    ET.SubElement(root, 'IComponent').text = _juce_memory_block(component)
    ET.SubElement(root, 'IEditController').text = _juce_memory_block(controller)
    xml = ET.tostring(root, encoding='utf-8')
    if len(xml) > 0xffffffff:
        raise ValueError('State XML exceeds the uint32 envelope length')
    return b'VC2!' + struct.pack('<I', len(xml)) + xml + b'\0'


def split_vst3_preset(data: bytes) -> tuple[str, dict[str, bytes]]:
    """Return the ASCII class UID and opaque chunks from a VST3 v1 preset.

    Validate the 48-byte header, hexadecimal 32-character UID, List pointer,
    complete List entries, and all chunk bounds before returning any data.
    Repeated tags and payload overlaps (including the header/List) fail.
    Unknown printable ASCII chunk tags and zero-length chunks are preserved.
    No commercial state interpretation or UID conversion is performed.
    """
    if not isinstance(data, bytes):
        raise TypeError('Preset data must be bytes')
    if len(data) < 48 or data[:4] != b'VST3':
        raise ValueError('Invalid or truncated VST3 preset header')
    if struct.unpack_from('<I', data, 4)[0] != 1:
        raise ValueError('Only VST3 preset version 1 is supported')
    try:
        uid = data[8:40].decode('ascii')
    except UnicodeDecodeError as exc:
        raise ValueError('Preset UID must be ASCII hexadecimal') from exc
    if len(uid) != 32 or any(c not in '0123456789abcdefABCDEF' for c in uid):
        raise ValueError('Preset UID must contain 32 hexadecimal characters')
    table = struct.unpack_from('<Q', data, 40)[0]
    if table < 48 or table > len(data) - 8 or data[table:table + 4] != b'List':
        raise ValueError('Invalid or truncated VST3 chunk List')
    count = struct.unpack_from('<I', data, table + 4)[0]
    if count > (len(data) - table - 8) // 20:
        raise ValueError('Truncated VST3 chunk List entries')
    table_end = table + 8 + count * 20
    entries, intervals, seen = [], [], set()
    for index in range(count):
        tag_bytes, start, size = struct.unpack_from('<4sqq', data, table + 8 + index * 20)
        if any(byte < 32 or byte > 126 for byte in tag_bytes):
            raise ValueError('Chunk tag must contain four printable ASCII characters')
        tag = tag_bytes.decode('ascii')
        if tag in seen:
            raise ValueError(f'Duplicate VST3 chunk tag: {tag}')
        seen.add(tag)
        stop = start + size
        if start < 48 or size < 0 or stop > len(data):
            raise ValueError(f'Invalid bounds for VST3 chunk: {tag}')
        if size and start < table_end and stop > table:
            raise ValueError(f'Chunk overlaps the VST3 List: {tag}')
        if size:
            intervals.append((start, stop, tag))
        entries.append((tag, start, stop))
    intervals.sort()
    for previous, current in zip(intervals, intervals[1:]):
        if current[0] < previous[1]:
            raise ValueError(f'Overlapping VST3 chunks: {previous[2]}, {current[2]}')
    return uid, {tag: data[start:stop] for tag, start, stop in entries}


def _note_velocities(event, report):
    if 'velocity' in event:
        minimum = 0 if 'velocity_normalized' in event else 1
        velocity = _integer(event['velocity'], 'velocity', minimum, 127)
    elif 'velocity_normalized' not in event:
        raise ValueError('Note requires velocity or velocity_normalized')
    if 'velocity_normalized' in event:
        normalized = _number(event['velocity_normalized'], 'velocity_normalized', 0, 1)
        if normalized == 0:
            raise ValueError('Note-on velocity_normalized must be positive')
        velocity = max(1, math.floor(normalized * 127 + .5))
        report['normalized_velocity_count'] += 1
        report['max_velocity_error'] = max(report['max_velocity_error'], abs(velocity / 127 - normalized))
    release = _integer(event.get('release_velocity', 64), 'release_velocity', 0, 127)
    normalized_values = [_number(event[key], key, 0, 1) for key in
                         ('release_normalized', 'release_velocity_normalized') if key in event]
    if normalized_values:
        if any(value != normalized_values[0] for value in normalized_values[1:]):
            raise ValueError('Conflicting normalized release velocity aliases')
        normalized = normalized_values[0]
        release = math.floor(normalized * 127 + .5)
        report['normalized_release_count'] += 1
        report['max_release_error'] = max(report['max_release_error'], abs(release / 127 - normalized))
    return velocity, release


def schedule_midi(events, beat_to_seconds, end_beats) -> tuple[list[tuple[bytes, float]], dict]:
    """Convert project-time event dictionaries into ``(MIDI bytes, seconds)``.

    Required common fields are type, beat, channel (zero-based 0..15). Types:
    note: pitch, positive duration, velocity and/or velocity_normalized;
    cc: controller, value; program: program; pitchbend: signed value -8192..8191.
    Note release_velocity defaults to 64. Optional release_normalized and
    release_velocity_normalized are aliases; conflicting aliases fail.

    Normalized values take precedence over validated integer velocity fields.
    A coarse velocity of zero is allowed only with a positive normalized value.
    Quantization rounds half upward to 7 bits; positive note-on values round
    to at least 1 to retain note-on semantics. The report includes counts and
    maximum absolute normalized error (including that minimum-one rule).
    Normalized note-on zero, unknown fields/types, invalid ranges, zero note
    durations and notes beyond end_beats all fail instead of being dropped.

    The supplied callback converts both note endpoints, already in project
    beats. No preroll or part offset is added. Sampled times must be finite,
    nonnegative and strictly increasing with beat. At equal time, note-offs
    precede CC/program/bend in original order, followed by note-ons. No panic,
    sustain release, note repair or musical changes are inserted. Events at
    end_beats are retained; rendering must include enough tail to consume them.
    """
    end = _number(end_beats, 'end_beats')
    if end == 0:
        raise ValueError('end_beats must be positive')
    if not callable(beat_to_seconds):
        raise ValueError('beat_to_seconds must be callable')
    try:
        events = list(events)
    except TypeError as exc:
        raise ValueError('events must be an iterable of event dictionaries') from exc
    report = dict(event_count=len(events), message_count=0, end_beats=end,
                  normalized_velocity_count=0, normalized_release_count=0,
                  max_velocity_error=0., max_release_error=0., max_normalized_error=0.)
    pending, beats = [], {0., end}
    common = {'type', 'beat', 'channel'}
    fields = {'note': {'pitch', 'duration', 'velocity', 'velocity_normalized', 'release_velocity',
                       'release_normalized', 'release_velocity_normalized'},
              'cc': {'controller', 'value'}, 'program': {'program'}, 'pitchbend': {'value'}}
    for index, event in enumerate(events):
        if not isinstance(event, Mapping) or not common.issubset(event):
            raise ValueError(f'Event {index} requires type, beat and channel')
        kind = event['type']
        if not isinstance(kind, str) or kind not in fields:
            raise ValueError(f'Unsupported MIDI event type at index {index}')
        if set(event) - common - fields[kind]:
            raise ValueError(f'Unknown fields in MIDI event {index}')
        required = {'pitch', 'duration'} if kind == 'note' else fields[kind]
        if not required.issubset(event):
            raise ValueError(f'Missing fields in {kind} event {index}')
        beat = _number(event['beat'], 'beat', 0, end)
        channel = _integer(event['channel'], 'channel', 0, 15)
        beats.add(beat)
        if kind == 'note':
            pitch = _integer(event['pitch'], 'pitch', 0, 127)
            duration = _number(event['duration'], 'duration')
            stop = _number(beat + duration, 'note end', 0, end)
            if duration == 0 or stop <= beat:
                raise ValueError('Note duration must advance project time')
            velocity, release = _note_velocities(event, report)
            pending.extend([(beat, 2, index, bytes([0x90 | channel, pitch, velocity])),
                            (stop, 0, index, bytes([0x80 | channel, pitch, release]))])
            beats.add(stop)
        elif kind == 'cc':
            controller = _integer(event['controller'], 'controller', 0, 127)
            value = _integer(event['value'], 'CC value', 0, 127)
            pending.append((beat, 1, index, bytes([0xb0 | channel, controller, value])))
        elif kind == 'program':
            program = _integer(event['program'], 'program', 0, 127)
            pending.append((beat, 1, index, bytes([0xc0 | channel, program])))
        else:
            value = _integer(event['value'], 'pitchbend', -8192, 8191) + 8192
            pending.append((beat, 1, index, bytes([0xe0 | channel, value & 127, value >> 7])))
    times, previous = {}, -1.
    for beat in sorted(beats):
        seconds = _number(beat_to_seconds(beat), 'beat_to_seconds result')
        if seconds <= previous:
            raise ValueError('beat_to_seconds must increase strictly with beat')
        times[beat], previous = seconds, seconds
    pending.sort(key=lambda item: (times[item[0]], item[1], item[2]))
    messages = [(raw, times[beat]) for beat, _, _, raw in pending]
    report.update(message_count=len(messages), end_seconds=times[end],
                  max_normalized_error=max(report['max_velocity_error'], report['max_release_error']))
    return messages, report


def _validated_blocks_input(messages, total_frames, sample_rate, block_frames):
    total = _integer(total_frames, 'total_frames', 0)
    block = _integer(block_frames, 'block_frames', 1)
    rate = _number(sample_rate, 'sample_rate')
    if rate == 0:
        raise ValueError('sample_rate must be positive')
    duration = _number(total / rate, 'render duration')
    try:
        messages = list(messages)
    except TypeError as exc:
        raise ValueError('messages must be iterable') from exc
    result, previous = [], -1.
    for message in messages:
        if not isinstance(message, (tuple, list)) or len(message) != 2:
            raise ValueError('Each MIDI message must be a (bytes, seconds) pair')
        raw, time = message
        if not isinstance(raw, bytes) or not raw:
            raise ValueError('MIDI message must contain bytes')
        kind = raw[0] & 0xf0
        expected_length = 2 if kind == 0xc0 else 3
        if kind not in (0x80, 0x90, 0xb0, 0xc0, 0xe0) or len(raw) != expected_length or any(v > 127 for v in raw[1:]):
            raise ValueError('Unsupported or invalid MIDI channel message')
        time = _number(time, 'MIDI message time')
        if time < previous:
            raise ValueError('MIDI messages must already be sorted by time')
        if time >= duration:
            raise ValueError('MIDI message at or beyond final render boundary; increase total_frames to include a tail')
        result.append((raw, time))
        previous = time
    return result, total, rate, block


def iter_midi_blocks(messages, total_frames, sample_rate, block_frames):
    """Yield ``(frame_count, [(bytes, block_relative_seconds), ...])``.

    Input messages must be time-sorted and use valid note-off/on, CC, program,
    or pitch-bend channel bytes. Validate the entire schedule before yielding.
    Windows are [start_frame / rate, end_frame / rate); exact boundary events
    belong only to the next block. Negative/nonfinite times and events at or
    beyond total_frames / rate are rejected explicitly. Include positive tail
    frames when an event occurs at the musical endpoint. Empty tail blocks and
    a short final block are yielded; zero frames with no messages yields none.
    This function applies no sample quantization or plug-in state changes.
    """
    messages, total, rate, block = _validated_blocks_input(messages, total_frames, sample_rate, block_frames)
    index = 0
    for start in range(0, total, block):
        count = min(block, total - start)
        left, right = start / rate, (start + count) / rate
        local = []
        while index < len(messages) and messages[index][1] < right:
            raw, seconds = messages[index]
            relative = seconds - left
            # A subtraction near a boundary can round up by one floating-point
            # ULP. Keep a time already verified inside this block half-open.
            if relative >= count / rate:
                relative = math.nextafter(count / rate, 0.)
            local.append((raw, relative))
            index += 1
        yield count, local


def render_instrument(plugin, messages, total_frames, sample_rate, block_frames,
                      buffer_size=512, channels=2):
    """Render a prepared callable instrument to float32 [channels, frames].

    The callable follows pedalboard's instrument API: MIDI messages positional,
    duration/sample_rate/num_channels/buffer_size/reset keyword arguments. The
    caller has already initialized the instrument and loaded its state. Every
    block uses reset=False, including the first and empty tail blocks, so the
    caller must supply a fresh or deliberately continued instrument instance.
    No plug-in is loaded on import, and no implicit flush/panic/reset is sent.

    Each returned block must have exactly the requested channel/frame shape
    and real finite samples representable as float32. Invalid schedules fail
    before any plug-in call. A plug-in failure leaves its state advanced; retry
    requires the caller to prepare its starting state again. This helper does
    not perform host routing, automation, latency compensation, or file I/O.
    """
    if not callable(plugin):
        raise ValueError('plugin must be an initialized callable instrument')
    channels = _integer(channels, 'channels', 1)
    buffer_size = _integer(buffer_size, 'buffer_size', 1)
    messages, total, rate, block = _validated_blocks_input(messages, total_frames, sample_rate, block_frames)
    import numpy as np

    output = np.empty((channels, total), dtype=np.float32)
    start = 0
    for count, local in iter_midi_blocks(messages, total, rate, block):
        rendered = plugin(local, duration=count / rate, sample_rate=rate,
                          num_channels=channels, buffer_size=buffer_size, reset=False)
        audio = np.asarray(rendered)
        if audio.shape != (channels, count):
            raise ValueError(f'Instrument returned shape {audio.shape}; expected {(channels, count)}')
        if audio.dtype.kind not in 'fiu' or not np.isfinite(audio).all():
            raise ValueError('Instrument returned non-real or nonfinite audio')
        with np.errstate(over='ignore', invalid='ignore'):
            audio = audio.astype(np.float32, copy=False)
        if not np.isfinite(audio).all():
            raise ValueError('Instrument audio cannot be represented as finite float32')
        output[:, start:start + count] = audio
        start += count
    return output


def cubase15_fader_gain(raw) -> float:
    """Observed Cubase 15 default +6 dB-scale law; finite raw float 0..32767.

    This is a specific observed fader law, not a universal host gain mapping.
    Values 0, 18688, 25856, 32767 map to gains 0, .5, 1, 2 respectively.
    """
    raw = _number(raw, 'fader raw', 0, 32767)
    if raw < 18688:
        return raw * raw / 698482688
    if raw <= 25856:
        return (raw - 11520) / 14336
    return 1 + (raw - 25856) / 6911


def cubase15_input_gain(raw) -> float:
    """Observed Cubase 15 InputGain law; finite raw float 0..32767, zero mutes.

    Other values use 256 ** (2 * raw / 32767 - 1). This observed mapping is
    opt-in and makes no claim about other hosts, scales, or host versions.
    """
    raw = _number(raw, 'InputGain raw', 0, 32767)
    return 0. if raw == 0 else 256 ** (2 * raw / 32767 - 1)

"""Experimental reader/relocator for an observed Cubase RIF2 archive variant.

Unknown data is preserved. This is not a specification for every CPR version.
The caller must fingerprint templates, require lossless round trips, and verify
written events. See references/cpr-format.md for the supported boundary.
"""
from dataclasses import dataclass, field
import bisect
import copy
import re
import struct
from cpr_fields import Reader, read_attrs


def merged_ranges(ranges):
    out = []
    for start, end in sorted(ranges):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(end, out[-1][1]))
        else:
            out.append((start, end))
    return out

@dataclass
class Raw:
    data: bytes
    origin: int | None = None
    scope: str = 'main'

@dataclass
class Node:
    name: str
    start: int
    data_start: int
    end: int
    header: Raw
    parts: list = field(default_factory=list)
    scope: str = 'main'
    class_version: int | None = None

    def walk(self):
        yield self
        for x in self.parts:
            if isinstance(x, Node):
                yield from x.walk()

    def get(self, name):
        return next((x for x in self.walk() if x.name == name))

    def raw_replace(self, start, end, data):
        for i, p in enumerate(self.parts):
            if isinstance(p, Node) and p.data_start <= start and (end <= p.end):
                return p.raw_replace(start, end, data)
            if isinstance(p, Raw) and p.origin is not None and (p.origin <= start <= end <= p.origin + len(p.data)):
                a = start - p.origin
                z = end - p.origin
                self.parts[i:i + 1] = [Raw(p.data[:a], p.origin, p.scope), Raw(data, None, p.scope), Raw(p.data[z:], end, p.scope)]
                return
        raise ValueError(('Cannot replace raw interval', self.name, hex(start), hex(end)))

    def clone(self, scope):
        n = copy.deepcopy(self)

        def visit(x):
            x.scope = scope
            if isinstance(x, Node):
                x.header.scope = scope
                for y in x.parts:
                    visit(y)
        visit(n)
        return n

class Archive:

    def __init__(self, b, start, end):
        self.b = b
        self.start = start
        self.end = end
        self.base = start + 8
        self.classes = {}
        candidates = []
        pat = b'\\xff{7}[\\xfe\\xff]\\x00\\x00\\x00([\\x02-\\x60])([A-Za-z][A-Za-z0-9_: ]+)\\x00'
        for m in re.finditer(pat, b[start:end]):
            if len(m[2]) + 1 != m[1][0]:
                continue
            o = m.start() + start
            q = m.end() + start
            ver = int.from_bytes(b[q:q + 2], 'big')
            if ver > 50:
                continue
            self.classes[o + 8 - self.base] = (m[2].decode(), q, o)
            if b[o:o + 8] == b'\xff' * 8:
                s = q + 10
                n = int.from_bytes(b[q + 2:s], 'big')
                if n <= end - s:
                    candidates.append((o, s, s + n, m[2].decode()))
        self.refs = []
        for m in re.finditer(b'(?=(\\x80\\x00\\x00\\x00[\\x00-\\x01][\\s\\S]{3}))', b[start:end]):
            o = m.start() + start
            k = int.from_bytes(m[1], 'big') & 9223372036854775807
            if k not in self.classes:
                continue
            self.refs.append((o, self.base + k))
            n = int.from_bytes(b[o + 8:o + 16], 'big')
            s = o + 16
            if n <= end - s:
                candidates.append((o, s, s + n, self.classes[k][0]))
        # Named attributes and plugin states are their own bounded encoding.
        # An int64 -1 followed by a field name resembles a class declaration;
        # interpreting it as one invents classes such as "SummingMode".
        attribute_leaves = []
        for o, s, e, name in candidates:
            if name == 'PDrumMapEntry':
                if b[o:o+8] == b'\xff'*8:
                    version = int.from_bytes(b[s-10:s-8], 'big')
                else:
                    key = int.from_bytes(b[o:o+8], 'big') & 0x7fffffffffffffff
                    q = self.classes[key][1]
                    version = int.from_bytes(b[q:q+2], 'big')
                # Observed v3 drum entry: 29 scalar bytes, a counted name,
                # a uint32 notation value, and two more counted strings.
                # A zero/length/name boundary can look like an object reference.
                if version == 3 and s+33 <= e:
                    try:
                        reader = Reader(b, s+29, e)
                        name_start = reader.pos
                        label = reader.string()
                        if not 0 < len(label) <= 4096 or not label.endswith(b'\0'):
                            raise ValueError('Unsupported drum name')
                        strings = [(name_start, reader.pos)]
                        reader.take(4)
                        for _ in range(2):
                            text_start = reader.pos
                            reader.string()
                            strings.append((text_start, reader.pos))
                        if reader.pos == e:
                            attribute_leaves.extend(strings)
                    except ValueError:
                        pass
            if name in ('FAttributes', 'MTrack'):
                attribute_leaves.append((s, e))
                continue
            attr_start = s + 29 if name == 'MInstrumentTrack' else s
            try:
                _, parsed_end = read_attrs(b, attr_start, e)
                if parsed_end == e or name == 'MInstrumentTrack':
                    attribute_leaves.append((attr_start, parsed_end))
            except (ValueError, UnicodeError, struct.error):
                pass
        attribute_leaves = merged_ranges(attribute_leaves)

        def in_attribute(p, width=1):
            i = bisect.bisect_right(attribute_leaves, (p+width-1, 10 ** 18)) - 1
            return i >= 0 and p < attribute_leaves[i][1]

        candidates = [c for c in candidates if not in_attribute(c[0])]
        self.classes = {k: v for k, v in self.classes.items() if not in_attribute(v[2])}
        self.refs = [r for r in self.refs if not in_attribute(r[0], 8)]
        midi_leaves = []
        for o, s, e, name in candidates:
            if name != 'MMidiPart':
                continue
            try:
                length = int.from_bytes(b[s:s + 4], 'big')
                if not 0 < length < 4096:
                    continue
                p = s + 4 + length + 20
                count = int.from_bytes(b[p:p + 4], 'big')
                p += 4
                if count == 0 and p == e:
                    midi_leaves.append((p, e))
                    continue
                if count > 1000000 or p >= e:
                    continue
                declarations = b[p]
                p += 1
                if declarations:
                    sysex = [z for x, y, z, n in candidates if n == 'MMidiSysex' and y == z and (p <= x < min(p + 2048, e))]
                    if not sysex:
                        continue
                    p = min(sysex)
                events_start = p
                for _ in range(count):
                    if p + 18 > e or b[p] not in (144, 176, 192, 224):
                        raise ValueError('MIDI header')
                    kind = b[p]
                    attributes = int.from_bytes(b[p + 14:p + 18], 'big')
                    p += 18
                    if attributes > 32:
                        raise ValueError('MIDI attributes')
                    for __ in range(attributes):
                        if p + 14 > e or int.from_bytes(b[p + 4:p + 6], 'big') not in (1, 4):
                            raise ValueError('MIDI field')
                        p += 14
                    if kind == 144:
                        p += 25
                    if p > e:
                        raise ValueError('MIDI extent')
                if p == e:
                    midi_leaves.append((events_start, e))
            except (ValueError, IndexError, struct.error):
                pass
        leaves = merged_ranges(attribute_leaves + midi_leaves + [(s, e) for o, s, e, name in candidates if name == 'MParamEvent' and e - s == 18])

        def in_leaf(p, width=1):
            i = bisect.bisect_right(leaves, (p+width-1, 10 ** 18)) - 1
            return i >= 0 and p < leaves[i][1]
        candidates = sorted(set((c for c in candidates if not in_leaf(c[0]))))
        self.refs = [r for r in self.refs if not in_leaf(r[0], 8)]
        self.classes = {k: v for k, v in self.classes.items() if not in_leaf(v[2])}
        stack = []
        self.nodes = {}
        self.root = Node('ARCH', start, start, end, Raw(b'', start))
        stack = [self.root]
        for o, s, e, name in candidates:
            while len(stack) > 1 and o >= stack[-1].end:
                stack.pop()
            if not (stack[-1].data_start <= o and e <= stack[-1].end):
                raise ValueError(('overlap', hex(o), name, stack[-1].name))
            if b[o:o+8] == b'\xff'*8:
                version = int.from_bytes(b[s-10:s-8], 'big')
            else:
                key = int.from_bytes(b[o:o+8], 'big') & 0x7fffffffffffffff
                q = self.classes[key][1]
                version = int.from_bytes(b[q:q+2], 'big')
            n = Node(name, o, s, e, Raw(b[o:s - 8], o), class_version=version)
            self.nodes[o] = n
            stack[-1].parts.append(n)
            stack.append(n)

        def fill(n):
            parts = []
            p = n.data_start
            for c in n.parts:
                if p < c.start:
                    parts.append(Raw(b[p:c.start], p))
                fill(c)
                parts.append(c)
                p = c.end
            if p < n.end:
                parts.append(Raw(b[p:n.end], p))
            n.parts = parts
        fill(self.root)
        self.object_refs = []
        dest = {n.data_start - self.base: n for n in self.root.walk() if n.name in ('MTempoTrackEvent', 'MSignatureTrackEvent', 'MAutomationTrack', 'MInstrumentTrackEvent', 'MFolderTrack', 'MDeviceTrackEvent')}
        excluded = [(n.start, n.end) for n in self.root.walk() if n.name in ('MTrack', 'MInstrumentTrack', 'FAttributes')] + midi_leaves + attribute_leaves
        for m in re.finditer(b'(?=(\\x00\\x00\\x00\\x00[\\x00-\\x01][\\s\\S]{3}))', b[start:end]):
            p = m.start() + start
            v = int.from_bytes(m[1], 'big')
            if v in dest and (not any((x < p+8 and p < y for x, y in excluded))):
                self.object_refs.append((p, dest[v].data_start))

    def validate_class_registry(self):
        seen = set()
        for name, _, _ in self.classes.values():
            if name in seen:
                raise ValueError(f'Duplicate archive class declaration: {name}')
            seen.add(name)
        if any(target > position for position, target in self.refs):
            raise ValueError('Forward archive class reference')
        return len(seen)

    def serialize(self, relocate=False, canonical_classes=False):
        if canonical_classes and not relocate:
            raise ValueError('Canonical class writing requires relocation')
        out = bytearray()
        spans = []
        payloads = {}
        registered = {}
        declarations = {o: (name, q, self.b[q:q+2]) for name, q, o in self.classes.values()}
        declaration_positions = sorted(declarations)
        self.canonicalized_class_count = 0

        def emit(data, origin, scope):
            if origin is not None and data:
                spans.append((origin, origin + len(data), len(out), scope))
            out.extend(data)

        def register(name, version):
            if name in registered:
                position, old_version = registered[name]
                if old_version != version:
                    raise ValueError(f'Conflicting archive class versions: {name}')
                return position
            # References address the uint32 class-name length, relative to +8.
            registered[name] = (len(out) + 8, version)
            return None

        def raw(r):
            if not canonical_classes or r.origin is None:
                emit(r.data, r.origin, r.scope)
                return
            cursor = 0
            i = bisect.bisect_left(declaration_positions, r.origin)
            while i < len(declaration_positions):
                old = declaration_positions[i]
                name, q, version = declarations[old]
                end = q + 2
                if end > r.origin + len(r.data):
                    break
                local = old - r.origin
                emit(r.data[cursor:local], r.origin + cursor, r.scope)
                if r.data[local:local+8] != b'\xff'*7+b'\xfe':
                    raise ValueError('Unexpected complete class declaration outside an object header')
                previous = register(name, version)
                if previous is None:
                    emit(r.data[local:end-r.origin], old, r.scope)
                else:
                    self.canonicalized_class_count += 1
                cursor = end - r.origin
                i += 1
            emit(r.data[cursor:], r.origin + cursor, r.scope)

        def node(n):
            if n.name != 'ARCH':
                declaration = declarations.get(n.header.origin) if canonical_classes else None
                if declaration is not None:
                    name, _, version = declaration
                    previous = register(name, version)
                    if previous is None:
                        emit(n.header.data, n.header.origin, n.scope)
                    else:
                        emit(struct.pack('>Q', 0x8000000000000000+previous-8), None, n.scope)
                        self.canonicalized_class_count += 1
                else:
                    raw(n.header)
                z = len(out)
                out.extend(b'\x00' * 8)
            s = len(out)
            payloads[n.scope, n.data_start] = s
            for p in n.parts:
                node(p) if isinstance(p, Node) else raw(p)
            if n.name != 'ARCH':
                struct.pack_into('>Q', out, z, len(out) - s)
        node(self.root)
        self.spans = spans
        self.payloads = payloads
        if not relocate:
            return bytes(out)
        by_scope = {}
        for a, z, p, scope in spans:
            by_scope.setdefault(scope, []).append((a, z, p))
        for v in by_scope.values():
            v.sort()

        def mapped(old, scope):
            for sc in [scope, 'main', 'track0']:
                vs = by_scope.get(sc, [])
                i = bisect.bisect_right(vs, (old, 10 ** 18, 10 ** 18)) - 1
                if i >= 0 and vs[i][0] <= old < vs[i][1]:
                    a, z, p = vs[i]
                    return p + old - a
            return None
        patched = 0
        def occurrences(references):
            ordered = sorted(references)
            positions = [r[0] for r in ordered]
            for a, z, new, scope in spans:
                i = bisect.bisect_left(positions, a)
                while i < len(ordered) and ordered[i][0] + 8 <= z:
                    oldref, target = ordered[i]
                    yield oldref, target, new + oldref - a, scope
                    i += 1
        for oldref, target, position, scope in occurrences(self.refs):
            if canonical_classes:
                name, _, _ = self.classes[target-self.base]
                dst = registered.get(name, (None, None))[0]
            else:
                dst = mapped(target, scope)
            if dst is None:
                raise ValueError(('Missing class reference', hex(oldref), hex(target), scope))
            struct.pack_into('>Q', out, position, 9223372036854775808 + dst - 8)
            patched += 1
        self.relocation_count = patched
        for oldref, target, position, scope in occurrences(self.object_refs):
            dst = payloads.get((scope, target), payloads.get(('main', target), payloads.get(('track0', target))))
            if dst is None:
                raise ValueError(('Missing object reference', hex(oldref), hex(target), scope))
            struct.pack_into('>Q', out, position, dst - 8)
            patched += 1
        self.relocation_count = patched
        return bytes(out)

def riff_chunks(b):
    if not (b[:4] == b'RIF2' and b[12:16] == b'NUND'):
        raise ValueError('Invalid CPR archive structure')
    if not int.from_bytes(b[4:12], 'big') == len(b) - 16:
        raise ValueError('Invalid CPR archive structure')
    p = 16
    out = []
    while p < len(b):
        n = int.from_bytes(b[p + 4:p + 12], 'big')
        if not p + 12 + n <= len(b):
            raise ValueError('Invalid CPR archive structure')
        out.append((b[p:p + 4], p, p + 12, p + 12 + n))
        p += 12 + n
    if not p == len(b):
        raise ValueError('Invalid CPR archive structure')
    return out

"""Bounded named-attribute decoder. Plugin state is handled as opaque bytes."""
from dataclasses import dataclass
import struct


@dataclass
class Field:
    name: str
    typ: int
    sub: int
    value: object


class Reader:
    def __init__(self, data, start, end):
        if not 0 <= start <= end <= len(data):
            raise ValueError("Invalid attribute bounds")
        self.data, self.pos, self.end = data, start, end
        self.budget = 250_000

    def take(self, size):
        if size < 0 or self.pos + size > self.end:
            raise ValueError("Truncated attributes")
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def number(self, fmt):
        return struct.unpack('>' + fmt, self.take(struct.calcsize('>' + fmt)))[0]

    def count(self):
        n = self.number('I')
        if n > 100_000:
            raise ValueError("Excessive attribute count")
        return n

    def string(self):
        return self.take(self.number('I'))

    def attrs(self, depth=0):
        if depth > 64:
            raise ValueError("Excessive attribute depth")
        out = []
        for _ in range(self.count()):
            self.budget -= 1
            if self.budget < 0:
                raise ValueError("Excessive attribute total")
            name = self.string()
            if not 0 < len(name) < 500 or not name.endswith(b'\0'):
                raise ValueError("Invalid attribute name")
            name = name[:-1].decode('utf-8')
            typ, sub = self.number('H'), 0
            if typ == 1:
                value = self.number('q')
            elif typ == 4:
                value = self.number('d')
            elif typ == 8:
                value = self.string()
            elif typ == 2:
                sub = self.number('H')
                if sub == 6:
                    value = self.attrs(depth + 1)
                elif sub == 7:
                    value = self.string()
                elif sub == 5:
                    value = [self.attrs(depth + 1) for _ in range(self.count())]
                elif sub in (2, 3):
                    value = [self.number('q' if sub == 2 else 'd') for _ in range(self.count())]
                elif sub == 4:
                    value = [self.string() for _ in range(self.count())]
                elif sub == 20:
                    value = (self.string(), self.take(8), self.attrs(depth + 1))
                elif sub == 21:
                    value = self.take(8)
                elif sub == 201:
                    value = []
                    for _ in range(self.count()):
                        if self.number('H') != 20:
                            raise ValueError("Unsupported object array subtype")
                        value.append((self.string(), self.take(8), self.attrs(depth + 1)))
                else:
                    raise ValueError(f"Unsupported attribute subtype: {sub}")
            else:
                raise ValueError(f"Unsupported attribute type: {typ}")
            out.append(Field(name, typ, sub, value))
        return out


def read_attrs(data, start, end):
    reader = Reader(data, start, end)
    return reader.attrs(), reader.pos


def walk(attrs, path=()):
    for field in attrs:
        key = path + (field.name,)
        yield key, field
        if field.typ == 2 and field.sub == 6:
            yield from walk(field.value, key)
        elif field.typ == 2 and field.sub == 5:
            for i, group in enumerate(field.value):
                yield from walk(group, key + (str(i),))
        elif field.typ == 2 and field.sub == 20:
            yield from walk(field.value[2], key)
        elif field.typ == 2 and field.sub == 201:
            for i, (_, _, group) in enumerate(field.value):
                yield from walk(group, key + (str(i),))


def text_value(field):
    raw = field.value
    if raw.endswith(b'\xef\xbb\xbf'):
        raw = raw[:-3]
    if raw.endswith(b'\0'):
        raw = raw[:-1]
    return raw.decode('utf-8')


def pack_string(value):
    return struct.pack('>I', len(value)) + value


def encode_attrs(attrs):
    def encode(f):
        head = pack_string(f.name.encode('utf-8') + b'\0') + struct.pack('>H', f.typ)
        if f.typ in (1, 4):
            return head + struct.pack('>q' if f.typ == 1 else '>d', f.value)
        if f.typ == 8:
            return head + pack_string(f.value)
        head += struct.pack('>H', f.sub)
        if f.sub == 6:
            return head + encode_attrs(f.value)
        if f.sub == 7:
            return head + pack_string(f.value)
        if f.sub in (4, 5, 2, 3):
            fn = (pack_string if f.sub == 4 else encode_attrs if f.sub == 5
                  else lambda v: struct.pack('>q' if f.sub == 2 else '>d', v))
            return head + struct.pack('>I', len(f.value)) + b''.join(fn(v) for v in f.value)
        if f.sub == 20:
            cls, ident, group = f.value
            return head + pack_string(cls) + ident + encode_attrs(group)
        if f.sub == 21:
            return head + f.value
        if f.sub == 201:
            return head + struct.pack('>I', len(f.value)) + b''.join(
                struct.pack('>H', 20) + pack_string(c) + i + encode_attrs(a)
                for c, i, a in f.value)
        raise ValueError("Unsupported attribute encoding")
    return struct.pack('>I', len(attrs)) + b''.join(encode(f) for f in attrs)

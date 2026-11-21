"""Static reader for the supported NIS/FastLZ Kontakt saved-state family.

No plugins are imported or executed. Optional pefile and pycryptodome imports
occur only when engine-table decoding is requested. Build fingerprints are
mandatory for that decoding mode. Product metadata and derived tables remain in memory.

See references/kontakt-static.md for format provenance and compatibility limits.
"""

from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from xml.etree import ElementTree as ET


class FormatError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise FormatError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unpack(fmt, data, offset, limit=None):
    end = len(data) if limit is None else limit
    require(0 <= offset <= offset + struct.calcsize(fmt) <= end <= len(data),
            f"Read outside declared bounds at {offset:#x}")
    return struct.unpack_from(fmt, data, offset)


@dataclass
class Item:
    start: int
    end: int
    local: int
    domain: bytes
    kind: int
    base: Item | None = None
    embedded: list = field(default_factory=list)

    def chain(self):
        current = self
        while current is not None:
            yield current
            current = current.base


@dataclass
class Container:
    start: int
    end: int
    item: Item
    children: list

    def walk(self):
        yield self
        for item in self.item.chain():
            for child in item.embedded:
                yield from child.walk()
        for child in self.children:
            yield from child.walk()


def parse_item(data, start, limit, depth):
    require(depth < 64, "NIS nesting exceeds supported limit")
    size, domain, kind, version = unpack("<Q4sII", data, start, limit)
    end = start + size
    require(version == 1 and size >= 20 and end <= limit, "Invalid item header")
    local, parent = start + 20, None
    if kind != 1:
        parent = parse_item(data, local, end, depth + 1)
        local = parent.end
    result = Item(start, end, local, domain, kind, parent)
    if domain == b"DSIN" and kind in (0x73, 0x74):
        version, flag = unpack("<IB", data, local, end)
        require(version == 1 and flag in (0, 1), "Unsupported subtree/encryption properties")
        if kind == 0x74:
            require(end - local == 5, "Unexpected EncryptionItem size")
        elif flag:
            raw_size, stored_size = unpack("<II", data, local + 5, end)
            require(raw_size > 0 and stored_size > 0 and local + 13 + stored_size == end,
                    "Invalid compressed block length")
        else:
            embedded = parse_container(data, local + 5, end, depth + 1)
            require(embedded.end == end, "Trailing bytes in uncompressed subtree")
            result.embedded.append(embedded)
    if domain == b"DSIN" and kind == 0x6D:
        version, checksum, chunk_version, chunk_size = unpack("<IIIQ", data, local, end)
        # PresetChunkItem can carry properties after the binary chunk.
        require(version == chunk_version == 1 and local + 20 + chunk_size <= end,
                "Invalid PresetChunkItem")
    return result


def parse_container(data, start, limit=None, depth=0):
    limit = len(data) if limit is None else limit
    require(depth < 64, "NIS nesting exceeds supported limit")
    size, version, magic = unpack("<QI4s", data, start, limit)
    end = start + size
    require(magic == b"hsin" and version == 1 and size >= 68 and end <= limit,
            "Invalid NIS container header")
    item = parse_item(data, start + 40, end, depth + 1)
    version, count = unpack("<II", data, item.end, end)
    require(version == 1 and count <= (end - item.end - 8) // 80,
            "Invalid child count")
    pos, children = item.end + 8, []
    for _ in range(count):
        unpack("<III", data, pos, end)  # Index/domain/type prefix.
        child = parse_container(data, pos + 12, end, depth + 1)
        children.append(child)
        pos = child.end
    require(pos == end, "NIS container length mismatch")
    return Container(start, end, item, children)


def find_roots(data):
    roots, search_from = [], 0
    while True:
        magic = data.find(b"hsin", search_from)
        if magic < 0:
            return roots
        search_from = magic + 4
        if magic < 12:
            continue
        try:
            root = parse_container(data, magic - 12)
        except FormatError:
            continue
        roots.append(root)
        search_from = root.end  # Skip nested signatures already covered by this tree.


def compressed_blocks(data, root):
    blocks = []
    for container in root.walk():
        chain = list(container.item.chain())
        encryption = next((i for i in chain if i.domain == b"DSIN" and i.kind == 0x74), None)
        encrypted = bool(data[encryption.local + 4]) if encryption else False
        for item in chain:
            if item.domain != b"DSIN" or item.kind != 0x73:
                continue
            compressed = bool(data[item.local + 4])
            require(compressed or not encrypted, "Encrypted uncompressed subtree is unsupported")
            if compressed:
                size, stored = unpack("<II", data, item.local + 5, item.end)
                blocks.append({"offset": item.local + 13, "stored_size": stored,
                               "decoded_size": size, "encrypted": encrypted})
    return blocks


def fastlz(data, expected, prefix=None):
    """Bounds-checked FastLZ levels 1/2. Prefix mode is only a candidate filter."""
    require(type(expected) is int and 0 < expected <= 128 * 1024 * 1024, "Decoded size exceeds 128 MiB limit")
    require(prefix is None or type(prefix) is int and 0 < prefix <= expected, "Invalid prefix size")
    require(bool(data), "Empty FastLZ data")
    level, control, pos = (data[0] >> 5) + 1, data[0] & 31, 1
    require(level in (1, 2), "Unsupported FastLZ level")
    output = bytearray()

    def read_byte():
        nonlocal pos
        require(pos < len(data), "Truncated FastLZ token")
        value = data[pos]
        pos += 1
        return value

    while True:
        if control >= 32:
            length, offset = (control >> 5) - 1, (control & 31) << 8
            if length == 6:
                while True:
                    extra = read_byte()
                    length += extra
                    if level == 1 or extra != 255:
                        break
            code = read_byte()
            distance = offset + code + 1
            if level == 2 and code == 255 and offset == (31 << 8):
                distance = (read_byte() << 8) + read_byte() + 8192
            length += 3
            require(0 < distance <= len(output) and len(output) + length <= expected,
                    "Invalid FastLZ back-reference or output size")
            for _ in range(length):
                output.append(output[-distance])
        else:
            length = control + 1
            require(pos + length <= len(data) and len(output) + length <= expected,
                    "Truncated FastLZ literals or output overflow")
            output.extend(data[pos:pos + length])
            pos += length
        if prefix is not None and len(output) >= prefix:
            return bytes(output)
        if pos == len(data):
            break
        control = read_byte()
    if prefix is None:
        require(len(output) == expected, "FastLZ output size mismatch")
    return bytes(output)


def read_table_input(engine, profile):
    require(engine.stat().st_size <= 512 * 1024 * 1024, "Engine exceeds 512 MiB limit")
    binary = engine.read_bytes()
    require(len(binary) == profile["engine_size"] and digest(binary) == profile["engine_sha256"],
            "Engine fingerprint differs from profile; statically analyze this build before using its RVAs")
    import pefile
    try:
        pe = pefile.PE(data=binary, fast_load=True)
    except pefile.PEFormatError as error:
        raise FormatError('Profile-matched engine is not a supported PE file') from error
    rva = int(profile["table_input_rva"], 0)
    size = profile["table_input_size"]
    require(size == 65536, "Unsupported table size")
    section = pe.get_section_by_rva(rva)
    require(section is not None and rva + size <= section.VirtualAddress + section.SizeOfRawData,
            "Table RVA does not refer to a complete disk-backed section range")
    offset = pe.get_offset_from_rva(rva)
    data = binary[offset:offset + size]
    require(len(data) == size and digest(data) == profile["table_input_sha256"],
            "Table input fingerprint mismatch")
    return data


def read_products(catalog):
    require(catalog.stat().st_size <= 32 * 1024 * 1024, "Catalog exceeds 32 MiB limit")
    products, seen = [], set()
    for product in ET.parse(catalog).getroot().iter("Product"):
        try:
            iv = bytes.fromhex(product.findtext(".//HU", ""))
            key = bytes.fromhex(product.findtext(".//JDX", ""))
        except ValueError:
            continue
        if len(iv) != 16 or len(key) not in (16, 24, 32) or (iv, key) in seen:
            continue
        seen.add((iv, key))
        products.append({"name": product.findtext("Name", ""),
                         "id": product.findtext("SNPID", ""), "iv": iv, "key": key})
    require(products, "Catalog contains no supported HU/JDX product metadata")
    return products


def transform_table(product, source):
    from Crypto.Cipher import AES
    return AES.new(product["key"], AES.MODE_CTR, nonce=b"",
                   initial_value=int.from_bytes(product["iv"], "big")).encrypt(source)


def decode_block(payload, block, source, products):
    expected = block["decoded_size"]
    require(type(expected) is int and 0 < expected <= 128 * 1024 * 1024, "Decoded size exceeds 128 MiB limit")
    require(len(payload) == block["stored_size"], "Stored payload size mismatch")
    if not block["encrypted"]:
        raw = fastlz(payload, expected)
        require(parse_container(raw, 0).end == len(raw), "Trailing bytes after decoded root")
        return raw, None
    require(products, "Encrypted block requires a matching engine, profile and catalog")
    for product in products:
        table = transform_table(product, source[:512])
        prefix = bytes(a ^ b for a, b in zip(payload[:512], table))
        try:
            probe = fastlz(prefix, expected, prefix=min(48, expected))
            require(len(probe) >= 16 and probe[12:16] == b"hsin", "Candidate magic mismatch")
            require(unpack("<QI", probe, 0) == (expected, 1), "Candidate header mismatch")
            table = transform_table(product, source)
            plain = bytes(value ^ table[index & 65535] for index, value in enumerate(payload))
            raw = fastlz(plain, expected)
            require(parse_container(raw, 0).end == len(raw), "Trailing bytes after decoded root")
        except FormatError:
            continue
        return raw, {"name": product["name"], "id": product["id"]}
    raise FormatError("No product metadata produced a fully validated decoded container")


def instrument_evidence(raw):
    """Return NKI references with matching length-prefixed UTF-16 name fields.

    These are saved-state references. This function does not infer MIDI slots,
    selected articulations or whether each reference is an active instrument.
    """
    result, seen = [], set()
    for match in re.finditer(rb"\.\x00[nN]\x00[kK]\x00[iI]\x00", raw):
        end = match.end()
        for count in range(5, min(4096, (end - 4) // 2) + 1):
            start = end - count * 2
            if unpack("<I", raw, start - 4)[0] != count:
                continue
            try:
                filename = raw[start:end].decode("utf-16le")
            except UnicodeDecodeError:
                continue
            if not filename.isprintable() or filename in seen:
                continue
            seen.add(filename)
            stem = filename.replace("\\", "/").rsplit("/", 1)[-1][:-4]
            if not stem:
                continue
            encoded, positions = stem.encode("utf-16le"), []
            pos = raw.find(encoded)
            while pos >= 0:
                if pos >= 4 and unpack("<I", raw, pos - 4)[0] == len(encoded) // 2:
                    positions.append(hex(pos))
                pos = raw.find(encoded, pos + 2)
            result.append({"nki_reference": filename, "name": stem,
                           "nki_offset": hex(start), "matching_name_offsets": positions,
                           "name_and_file_agree": bool(positions)})
            break
    return result

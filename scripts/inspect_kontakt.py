#!/usr/bin/env python3
"""Identify saved Kontakt instrument references from CPR or extracted state.

Reads local files only. Does not load plugins, edit projects, or emit raw state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
from xml.etree import ElementTree

from kontakt_state import (FormatError, require, digest, read_table_input,
                           read_products, find_roots, compressed_blocks,
                           decode_block, parse_container, instrument_evidence)

LIMIT = 128 * 1024 * 1024


def read_bounded(path, limit=LIMIT):
    require(path.stat().st_size <= limit, f"Input exceeds {limit // 1048576} MiB limit")
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, "Input grew beyond size limit")
    return data


def load_settings(args):
    """Return optional decoding inputs, resolving configured paths next to the JSON."""
    default = Path(__file__).resolve().parents[1] / 'private' / 'kontakt-static.json'
    config = args.config if args.config is not None else (default if default.is_file() else None)
    names = ('engine', 'profile', 'catalog')
    if config is None and all(getattr(args, name) is None for name in names):
        return None
    values = {}
    if config is not None:
        values = json.loads(read_bounded(config, 1024 * 1024).decode('utf-8-sig'))
        require(isinstance(values, dict), "Config must be a JSON object")
    result = {}
    for name in names:
        override = getattr(args, name)
        if override is not None:
            result[name] = override.resolve()
        else:
            value = values.get(name)
            require(isinstance(value, str) and bool(value),
                    f"Supply --{name} or {name} in private/kontakt-static.json")
            path = Path(value)
            result[name] = (path if path.is_absolute() else config.parent / path).resolve()
    return result


def extract_cpr(data):
    """Observed instrument-attribute layout; no MIDI-part or audio-track limits."""
    from cpr_archive import Archive, riff_chunks
    from cpr_fields import read_attrs, encode_attrs, walk, text_value

    chunks = riff_chunks(data)
    roots = {}
    for i, (tag, _, start, end) in enumerate(chunks):
        if tag != b'ROOT':
            continue
        require(end - start >= 4, "Truncated ROOT")
        size = struct.unpack_from('>I', data, start)[0]
        require(0 < size <= end - start - 4, "Invalid ROOT name length")
        name = data[start + 4:start + 4 + size].rstrip(b'\0').decode('utf-8')
        require(name not in roots and i + 1 < len(chunks) and chunks[i + 1][0] == b'ARCH',
                "Unsupported ROOT/ARCH pairing")
        roots[name] = i + 1
    require('Arrangement1' in roots, "Arrangement1 archive is required")
    _, _, start, end = chunks[roots['Arrangement1']]
    archive = Archive(data, start, end)
    require(archive.serialize(True) == data[start:end], "Arrangement1 byte round trip failed")
    tracks = [n for n in archive.root.walk() if n.name == 'MInstrumentTrackEvent']
    require(len(tracks) <= 128, "More than 128 instrument tracks")
    rows = []
    for index, track in enumerate(tracks, 1):
        entry = {'track_index': index, 'track_name': None, 'plugin_name': None,
                 'plugin_uid': None, 'status': 'unresolved', 'blocks': []}
        rows.append((entry, None))
        try:
            instruments = [n for n in track.walk() if n.name == 'MInstrumentTrack']
            require(len(instruments) == 1, "Expected one MInstrumentTrack object")
            instrument = instruments[0]
            # This relative prefix belongs to the observed archive layout, not a
            # file offset. Attribute round trip and required paths guard it.
            attrs_start = instrument.data_start + 29
            attrs, attrs_end = read_attrs(data, attrs_start, instrument.end)
            require(encode_attrs(attrs) == data[attrs_start:attrs_end],
                    "Instrument attributes failed byte round trip")
            flat_fields = list(walk(attrs))
            fields = dict(flat_fields)
            required = [('Name', 'String'), ('Synth Slot', 'Plugin', 'Plugin Name'),
                        ('Synth Slot', 'Plugin', 'Plugin UID', 'GUID'),
                        ('Synth Slot', 'Plugin', 'audioComponent')]
            require(all(p in fields for p in required), "Missing required instrument attributes")
            require(all(sum(path == p for path, _ in flat_fields) == 1 for p in required),
                    "Duplicate required instrument attribute path")
            require(all(isinstance(fields[p].value, bytes) for p in required[:3]),
                    "Track name, plugin name and plugin UID must be byte strings")
            entry.update(track_name=text_value(fields[required[0]]),
                         plugin_name=text_value(fields[required[1]]),
                         plugin_uid=text_value(fields[required[2]]))
            if 'kontakt' not in entry['plugin_name'].lower():
                entry['status'] = 'skipped_non_kontakt'
                continue
            state = fields[required[3]].value
            require(isinstance(state, bytes), "audioComponent is not a byte string")
            entry.update(state_bytes=len(state), state_sha256=digest(state))
            rows[-1] = entry, state
        except (ValueError, KeyError, TypeError, UnicodeError, struct.error) as error:
            entry['error'] = str(error)
    return rows, {'arrangement1_byte_identical_roundtrip': True,
                  'instrument_tracks_seen': len(tracks),
                  'instrument_index_basis': 'one-based MInstrumentTrackEvent archive order'}


def identify_state(state, source, products):
    """Return evidence only; no active-slot, articulation or sound inference."""
    require(len(state) <= LIMIT, "State exceeds 128 MiB limit")
    if not state:
        return {'status': 'empty_state', 'blocks': [], 'error': 'No saved component bytes'}
    roots = find_roots(state)
    if not roots:
        return {'status': 'unresolved', 'blocks': [], 'error': 'No validated NIS container found'}
    records = []
    for root_index, root in enumerate(roots):
        try:
            blocks = compressed_blocks(state, root)
        except FormatError as error:
            records.append({'root_index': root_index, 'status': 'unresolved', 'error': str(error)})
            continue
        # Plain NIS roots can already hold a saved instrument reference.
        if not blocks:
            raw = state[root.start:root.end]
            ev = instrument_evidence(raw)
            records.append({'root_index': root_index, 'offset': root.start,
                            'decoded_size': len(raw), 'decoded_sha256': digest(raw),
                            'length_and_tree_validated': True,
                            'block_offset_basis': 'component_state_bytes',
                            'instrument_offset_basis': 'NIS_root_bytes',
                            'status': evidence_status(ev), 'instruments': ev})
        for block_index, block in enumerate(blocks):
            record = dict(block, root_index=root_index, block_index=block_index,
                          status='unresolved', block_offset_basis='component_state_bytes',
                          instrument_offset_basis='decoded_NIS_bytes')
            records.append(record)
            try:
                require(block['decoded_size'] <= LIMIT, "Decoded block exceeds 128 MiB limit")
                offset = block['offset']
                raw, product = decode_block(state[offset:offset + block['stored_size']],
                                            block, source, products)
                require(not compressed_blocks(raw, parse_container(raw, 0)),
                        "Nested compressed subtree needs another decoding layer")
                ev = instrument_evidence(raw)
                record.update(status=evidence_status(ev), instruments=ev,
                              product_metadata_matched=product is not None, decoded_sha256=digest(raw),
                              length_and_tree_validated=True)
            except FormatError as error:
                record['error'] = str(error)
    statuses = [record['status'] for record in records]
    if statuses and all(status == 'identified_saved_reference' for status in statuses):
        status = 'identified_saved_reference'
    elif any(status == 'identified_saved_reference' for status in statuses):
        status = 'partial'
    else:
        status = 'unresolved'
    return {'status': status, 'blocks': records,
            'identity_scope': 'saved references; active slots, MIDI routing and audibility not verified'}


def evidence_status(evidence):
    if not evidence:
        return 'decoded_without_instrument_reference'
    if not all(item['name_and_file_agree'] for item in evidence):
        return 'decoded_with_unconfirmed_name'
    return 'identified_saved_reference'


def markdown(report):
    def escape(s):
        return str(s or '').replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')
    lines = ['# Kontakt saved-state identification', '',
             'Static local-file inspection. No DAW or plugin was loaded.', '',
             f"Source SHA-256: `{report['sha256_before']}`", '',
             '| Track | Plugin | Status | Saved NKI references |',
             '|---|---|---|---|']
    for row in report['tracks']:
        refs = [i['nki_reference'] for b in row.get('blocks', []) for i in b.get('instruments', [])]
        label = (f"{row['track_index']}: {row['track_name']}" if row['track_index'] is not None
                 else 'Unknown track (standalone state)')
        lines.append('| ' + ' | '.join(escape(x) for x in (
            label, row.get('plugin_name'), row['status'],
            '; '.join(refs) or row.get('error', ''))) + ' |')
    lines += ['', 'See report.json for bounds validation, errors and name/reference offsets.',
              'Multiple references do not establish active slot or MIDI-channel routing.',
              f"Source unchanged: {report['source_unchanged']}. Runtime/audio verification: not performed.", '']
    return '\n'.join(lines)


def run(args):
    require(not args.out.exists(), 'Output directory exists; choose a new directory')
    settings = load_settings(args)
    table_input, products, engine_sha256 = b'', [], None
    if settings is not None:
        profile = json.loads(read_bounded(settings['profile'], 1024 * 1024).decode('utf-8-sig'))
        require(isinstance(profile, dict), 'Engine profile must be a JSON object')
        table_input = read_table_input(settings['engine'], profile)
        products = read_products(settings['catalog'])
        engine_sha256 = profile['engine_sha256']
    data = read_bounded(args.input)
    before = digest(data)
    kind = args.input_kind
    if kind == 'auto':
        kind = 'cpr' if args.input.suffix.lower() == '.cpr' else 'state'
    if kind == 'cpr':
        rows, extraction = extract_cpr(data)
    else:
        rows = [({'track_index': None, 'track_name': None, 'source_label': args.input.name,
                  'plugin_name': 'Kontakt (state input)', 'plugin_uid': None,
                  'state_bytes': len(data), 'state_sha256': before}, data)]
        extraction = {'state_input': True, 'track_mapping_not_available': True}
    for row, state in rows:
        if state is not None:
            row.update(identify_state(state, table_input, products))
    after = digest(read_bounded(args.input))
    require(before == after, 'Source changed during analysis; repeat with a stable saved file')
    tracks = [row for row, _ in rows]
    eligible = [r for r in tracks if r['status'] != 'skipped_non_kontakt']
    success = bool(eligible) and all(r['status'] == 'identified_saved_reference' for r in eligible)
    report = {'schema_version': 1, 'source': str(args.input.resolve()), 'input_kind': kind,
              'sha256_before': before, 'sha256_after': after, 'source_unchanged': True,
              'runtime_loaded': False, 'audio_verified': False,
              'engine_sha256': engine_sha256, 'extraction': extraction,
              'result': 'complete' if success else 'partial_or_unresolved', 'tracks': tracks}
    # No raw states, decoded NIS, catalog secrets or derived tables are written.
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.out / 'report.md').write_text(markdown(report), encoding='utf-8')
    for row in tracks:
        label = (f"{row['track_index']} {row.get('track_name')}" if row['track_index'] is not None
                 else 'Standalone state (track unknown)')
        print(f"{label}: {row['status']}")
    print(f"Report: {(args.out / 'report.json').resolve()}")
    return 0 if success else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--input-kind', choices=('auto', 'cpr', 'state'), default='auto')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--engine', type=Path)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError, KeyError, TypeError, ImportError, ElementTree.ParseError,
            struct.error) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())

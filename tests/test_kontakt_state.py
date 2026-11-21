"""Synthetic regression evidence; no commercial project or plugin data."""
import argparse
import contextlib
import io
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import kontakt_state as ks
import inspect_kontakt as cli


def field(text):
    raw = text.encode('utf-16le')
    return struct.pack('<I', len(raw) // 2) + raw


def item(kind=1, props=b'', base=b'', domain=b'DSIN'):
    return struct.pack('<Q4sII', 20 + len(base) + len(props), domain, kind, 1) + base + props


def container(content=None):
    content = item() if content is None else content
    size = 40 + len(content) + 8
    return struct.pack('<QI4s', size, 1, b'hsin') + b'\0' * 24 + content + struct.pack('<II', 1, 0)


def literal_compress(raw):
    return b''.join(bytes([len(raw[n:n+32]) - 1]) + raw[n:n+32] for n in range(0, len(raw), 32))


def packed_container(raw):
    packed = literal_compress(raw)
    subtree = item(0x73, struct.pack('<IBII', 1, 1, len(raw), len(packed)) + packed, item())
    return container(subtree)


class FastLZTests(unittest.TestCase):
    def test_literals_and_valid_overlap(self):
        self.assertEqual(ks.fastlz(b'\x00A\x20\x00', 4), b'AAAA')
        original = bytes(range(80))
        self.assertEqual(ks.fastlz(literal_compress(original), len(original)), original)

    def test_truncation_backref_and_wrong_output_size(self):
        for data, expected in [(b'\x02ab', 3), (b'\x00A\x20\x02', 4),
                               (b'\x00A', 2), (b'\x00A\x20\x00', 3), (b'\x00A\x20', 4)]:
            with self.subTest(data=data), self.assertRaises(ks.FormatError):
                ks.fastlz(data, expected)

    def test_prefix_cannot_bypass_decoded_limit(self):
        with self.assertRaises(ks.FormatError):
            ks.fastlz(b'\x00A', 128 * 1024 * 1024 + 1, prefix=1)


class NISTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('Crypto'), 'Optional pycryptodome is unavailable')
    def test_encrypted_candidates_and_sensitive_metadata_stay_private(self):
        raw = container(item(props=field('Toy Flute') + field('Toy Flute.nki')))
        source = bytes(range(256)) * 256
        right = {'name': 'SyntheticPrivateProduct', 'id': 'SECRET_SYNTHETIC_ID',
                 'key': bytes(range(16)), 'iv': bytes(reversed(range(16)))}
        wrong = {'name': 'WrongSyntheticProduct', 'id': 'WRONG',
                 'key': b'X' * 16, 'iv': b'Y' * 16}
        table = ks.transform_table(right, source)
        packed = literal_compress(raw)
        payload = bytes(v ^ table[i & 65535] for i, v in enumerate(packed))
        block = {'decoded_size': len(raw), 'stored_size': len(payload), 'encrypted': True}
        with self.assertRaises(ks.FormatError):
            ks.decode_block(payload, block, source, [wrong])
        decoded, product = ks.decode_block(payload, block, source, [wrong, right])
        self.assertEqual(decoded, raw)
        self.assertEqual(product['name'], right['name'])
        subtree = item(0x73, struct.pack('<IBII', 1, 1, len(raw), len(payload)) + payload, item())
        state = container(item(0x74, struct.pack('<IB', 1, 1), subtree))
        result = cli.identify_state(state, source, [wrong, right])
        self.assertEqual(result['status'], 'identified_saved_reference')
        self.assertTrue(result['blocks'][0]['product_metadata_matched'])
        text = json.dumps(result)
        for secret in [right['name'], right['id'], right['key'].hex(), right['iv'].hex(),
                       '"key"', '"iv"']:
            self.assertNotIn(secret, text)

    def test_length_header_version_and_trailing_bytes_rejected(self):
        raw = container()
        self.assertEqual(ks.parse_container(raw, 0).end, len(raw))
        for mutated in [raw[:-1], struct.pack('<Q', len(raw)+1)+raw[8:],
                        raw[:8]+struct.pack('<I', 2)+raw[12:],
                        struct.pack('<Q', len(raw)+1)+raw[8:]+b'X']:
            with self.subTest(raw=mutated), self.assertRaises(ks.FormatError):
                ks.parse_container(mutated, 0)

    def test_names_require_length_prefixed_corresponding_name(self):
        self.assertEqual(ks.instrument_evidence(b'Toy Flute.nki'), [])
        no_name = ks.instrument_evidence(field('Toy Flute.nki'))
        self.assertFalse(no_name[0]['name_and_file_agree'])
        evidence = ks.instrument_evidence(field('Toy Flute') + field('folder/Toy Flute.nki'))
        self.assertEqual(evidence[0]['name'], 'Toy Flute')
        self.assertTrue(evidence[0]['name_and_file_agree'])

    def test_empty_basename_is_not_instrument_evidence(self):
        self.assertEqual(ks.instrument_evidence(field('') + field('folder/.nki')), [])

    def test_compressed_and_plain_saved_reference(self):
        raw = container(item(props=field('Toy Flute') + field('Toy Flute.nki')))
        for state in [raw, packed_container(raw)]:
            result = cli.identify_state(state, b'', [])
            self.assertEqual(result['status'], 'identified_saved_reference')
            self.assertEqual(result['blocks'][0]['instruments'][0]['name'], 'Toy Flute')
            self.assertTrue(result['blocks'][0]['length_and_tree_validated'])

    def test_nested_compression_fails_closed(self):
        state = packed_container(packed_container(container()))
        result = cli.identify_state(state, b'', [])
        self.assertEqual(result['status'], 'unresolved')
        self.assertIn('Nested compressed', result['blocks'][0]['error'])

    def test_good_and_unresolved_roots_produce_partial_result(self):
        good = container(item(props=field('Toy Flute') + field('Toy Flute.nki')))
        result = cli.identify_state(good + container(), b'', [])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(len(result['blocks']), 2)
        self.assertEqual(result['blocks'][0]['block_offset_basis'], 'component_state_bytes')
        self.assertEqual(result['blocks'][1]['offset'], len(good))

    def test_no_reference_and_multiple_references_are_distinguished(self):
        self.assertEqual(cli.identify_state(container(), b'', [])['status'], 'unresolved')
        raw = container(item(props=field('Toy Flute') + field('Toy Flute.nki') +
                             field('Toy Oboe') + field('Toy Oboe.nki')))
        result = cli.identify_state(raw, b'', [])
        self.assertEqual(len(result['blocks'][0]['instruments']), 2)
        self.assertIn('active slots', result['identity_scope'])
        self.assertNotIn('active_slot', json.dumps(result))

    def test_wrong_payload_and_invalid_container_cannot_pass_decode(self):
        raw = container()
        packed = literal_compress(raw)
        with self.assertRaises(ks.FormatError):
            ks.decode_block(packed, {'decoded_size': len(raw), 'stored_size': len(packed)+1,
                                    'encrypted': False}, b'', [])
        garbage = literal_compress(b'garbage')
        with self.assertRaises(ks.FormatError):
            ks.decode_block(garbage, {'decoded_size': 7, 'stored_size': len(garbage),
                                     'encrypted': False}, b'', [])


class InputOutputTests(unittest.TestCase):
    def test_unknown_string_type_and_duplicate_attribute_are_track_errors(self):
        import cpr_archive
        import cpr_fields
        root_name = b'Arrangement1\0'
        root = struct.pack('>I', len(root_name)) + root_name
        payload = b'synthetic archive'
        data = root + payload
        instrument = SimpleNamespace(name='MInstrumentTrack', data_start=0, end=29)
        track = SimpleNamespace(name='MInstrumentTrackEvent', walk=lambda: iter([instrument]))
        archive = SimpleNamespace(root=SimpleNamespace(walk=lambda: iter([track])),
                                  serialize=lambda relocate: payload)
        paths = [('Name', 'String'), ('Synth Slot', 'Plugin', 'Plugin Name'),
                 ('Synth Slot', 'Plugin', 'Plugin UID', 'GUID'),
                 ('Synth Slot', 'Plugin', 'audioComponent')]
        values = [b'Unrenamed\0', b'Kontakt\0', b'UID\0', b'state']
        valid = [(p, SimpleNamespace(value=v)) for p, v in zip(paths, values)]
        bad_type = [(paths[0], SimpleNamespace(value=42))] + valid[1:]
        duplicate = valid + [valid[0]]
        for fields, expected in [(bad_type, 'must be byte strings'),
                                 (duplicate, 'Duplicate required')]:
            with patch.object(cpr_archive, 'riff_chunks', return_value=[
                    (b'ROOT', 0, 0, len(root)), (b'ARCH', 0, len(root), len(data))]), \
                    patch.object(cpr_archive, 'Archive', return_value=archive), \
                    patch.object(cpr_fields, 'read_attrs', return_value=([], 29)), \
                    patch.object(cpr_fields, 'encode_attrs', return_value=b''), \
                    patch.object(cpr_fields, 'walk', return_value=iter(fields)):
                rows, _ = cli.extract_cpr(data)
                self.assertEqual(rows[0][0]['status'], 'unresolved')
                self.assertIn(expected, rows[0][0]['error'])
                self.assertIsNone(rows[0][1])

    def test_bad_engine_hash_rejected_before_optional_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = Path(tmp) / 'engine.bin'
            engine.write_bytes(b'fake engine')
            with self.assertRaisesRegex(ks.FormatError, 'fingerprint'):
                ks.read_table_input(engine, {'engine_size': 11, 'engine_sha256': '0'*64})

    def test_relative_config_paths_and_cli_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / 'settings.json'
            config.write_text(json.dumps({'engine': 'engine.bin', 'profile': 'profile.json',
                                          'catalog': 'catalog.xml'}))
            override = root / 'new-engine.bin'
            args = argparse.Namespace(config=config, engine=override, profile=None, catalog=None)
            settings = cli.load_settings(args)
            self.assertEqual(settings['engine'], override.resolve())
            self.assertEqual(settings['profile'], (root/'profile.json').resolve())

    def test_existing_output_blocks_before_reading_any_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.bin'
            path.write_bytes(b'original')
            with contextlib.redirect_stderr(io.StringIO()):
                code = cli.main([str(path), '--out', str(path)])
            self.assertEqual(code, 1)
            self.assertEqual(path.read_bytes(), b'original')

    def test_install_without_private_config_reports_plain_and_encrypted_state(self):
        raw = container(item(props=field('Toy Flute') + field('Toy Flute.nki')))
        plain = packed_container(raw)
        dummy_payload = b'x'
        subtree = item(0x73, struct.pack('<IBII', 1, 1, len(raw), len(dummy_payload))
                       + dummy_payload, item())
        encrypted = container(item(0x74, struct.pack('<IB', 1, 1), subtree))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'input.state'
            out = root / 'result'
            source.write_bytes(plain + encrypted)
            with patch.object(cli, '__file__', str(root / 'scripts' / 'inspect_kontakt.py')), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = cli.main([str(source), '--out', str(out)])
            self.assertEqual(code, 2)
            report = json.loads((out / 'report.json').read_text())
            self.assertIsNone(report['engine_sha256'])
            track, = report['tracks']
            self.assertEqual(track['status'], 'partial')
            first, second = track['blocks']
            self.assertEqual(first['instruments'][0]['name'], 'Toy Flute')
            self.assertEqual(second['status'], 'unresolved')
            self.assertIn('engine, profile and catalog', second['error'])

    def test_cpr_unknown_input_refused(self):
        with self.assertRaises(ValueError):
            cli.extract_cpr(b'not a CPR')

    def test_empty_and_invalid_state_report_unresolved_without_throwing(self):
        self.assertEqual(cli.identify_state(b'', b'', [])['status'], 'empty_state')
        self.assertEqual(cli.identify_state(b'unknown format', b'', [])['status'], 'unresolved')

    def test_unresolved_cli_writes_safe_report_and_nonzero_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'unknown.state'
            source.write_bytes(b'unknown saved state')
            profile = root / 'profile.json'
            profile.write_text(json.dumps({'engine_sha256': 'synthetic engine fingerprint'}))
            out = root / 'result'
            with patch.object(cli, 'read_table_input', return_value=b''), \
                    patch.object(cli, 'read_products', return_value=[]), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = cli.main([str(source), '--engine', str(root/'engine'), '--profile', str(profile),
                                 '--catalog', str(root/'catalog'), '--out', str(out)])
            self.assertEqual(code, 2)
            report = json.loads((out/'report.json').read_text())
            self.assertTrue(report['source_unchanged'])
            self.assertIsNone(report['tracks'][0]['track_index'])
            self.assertIsNone(report['tracks'][0]['track_name'])
            self.assertFalse(report['runtime_loaded'])
            self.assertEqual({p.name for p in out.iterdir()}, {'report.json', 'report.md'})
            self.assertNotIn('unknown saved state', (out/'report.json').read_text())

    def test_changed_source_prevents_report_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.state'
            source.write_bytes(b'initial state')
            profile = root/'profile.json'
            profile.write_text(json.dumps({'engine_sha256': 'synthetic'}))
            def concurrent_change(*args):
                source.write_bytes(b'changed by a simulated other process')
                return {'status': 'unresolved', 'blocks': []}
            with patch.object(cli, 'read_table_input', return_value=b''), \
                    patch.object(cli, 'read_products', return_value=[]), \
                    patch.object(cli, 'identify_state', side_effect=concurrent_change), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = cli.main([str(source), '--engine', str(root/'engine'), '--profile', str(profile),
                                 '--catalog', str(root/'catalog'), '--out', str(root/'result')])
            self.assertEqual(code, 1)
            self.assertFalse((root/'result').exists())


if __name__ == '__main__':
    unittest.main()

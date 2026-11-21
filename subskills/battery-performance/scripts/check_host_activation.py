#!/usr/bin/env python3
"""Read saved Cubase instrument-slot activation flags; never run a plugin."""

import argparse
import json
from pathlib import Path
import re
import struct
import sys

PARENT_SCRIPTS = Path(__file__).resolve().parents[3] / 'scripts'
sys.path.insert(0, str(PARENT_SCRIPTS))

from cpr_fields import walk, text_value
from cpr_scaffold import read_donor, instrument_attributes
from cubase_project import exactly

# Observed Battery 4 VST-compatible UID. Other builds require explicit identity.
OBSERVED_UID = '5653544E426134626174746572792034'
PLUGIN_PATH = ('Synth Slot', 'Plugin')


def uid_argument(value):
    if not re.fullmatch(r'[0-9a-fA-F]{32}', value):
        raise argparse.ArgumentTypeError('Expected a 32-character hexadecimal plugin UID')
    return value.upper()


def positive_index(value):
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('Expected a positive instrument-track index') from error
    if number < 1:
        raise argparse.ArgumentTypeError('Instrument-track indices start at 1')
    return number


def one_field(fields, path):
    found = [field for key, field in fields if key == path]
    if len(found) != 1:
        raise ValueError('Missing or ambiguous attribute: ' + '/'.join(path))
    return found[0]


def string_field(fields, path):
    field = one_field(fields, path)
    if field.typ != 8 or not isinstance(field.value, bytes):
        raise ValueError('Unsupported string attribute: ' + '/'.join(path))
    return text_value(field)


def inspect_track(data, node, index, allowed_uids):
    record = {'instrument_track_index': index, 'status': 'unresolved'}
    try:
        attrs, _, _ = instrument_attributes(data, exactly(node.walk(), 'MInstrumentTrack'))
        fields = list(walk(attrs))
        record['name'] = string_field(fields, ('Name', 'String'))
        identity = string_field(fields, PLUGIN_PATH + ('IDString',))
        record['plugin_id_string'] = identity
        match = re.fullmatch(r'([0-9a-fA-F]{32})(?:-[0-9]+)?', identity)
        if match is None:
            raise ValueError('Unsupported plugin IDString representation')
        uid = match.group(1).upper()
        record['plugin_uid'] = uid
        record['identity_confirmed'] = uid in allowed_uids
        if not record['identity_confirmed']:
            record['reason'] = 'UID is outside the explicitly supported identity set'
            return record
        flag = one_field(fields, PLUGIN_PATH + ('Active',))
        if flag.typ != 1 or type(flag.value) is not int or flag.value not in (0, 1):
            raise ValueError('Active is not a supported type-1 integer flag (0 or 1)')
        record['saved_active'] = flag.value
        record['status'] = 'active' if flag.value == 1 else 'inactive'
        if flag.value == 0:
            record['reason'] = 'Saved Cubase plugin slot is deactivated'
    except (ValueError, KeyError, UnicodeError, TypeError, AttributeError) as error:
        record['reason'] = str(error)
    return record


def inspect_project(project, selected, allowed_uids):
    data, _, tracks = read_donor(project)
    records = [inspect_track(data, node, index, allowed_uids)
               for index, node in enumerate(tracks, 1)]
    wanted = set(selected)
    if wanted:
        checked = [record for record in records if record['instrument_track_index'] in wanted]
        checked += [{'instrument_track_index': index, 'status': 'unresolved',
                     'reason': 'Instrument-track index is outside this saved project'}
                    for index in sorted(wanted) if index > len(tracks)]
    else:
        checked = [record for record in records if record.get('identity_confirmed')]
    checked_indices = {record['instrument_track_index'] for record in checked}
    skipped = [record for record in records if record['instrument_track_index'] not in checked_indices]
    ok = bool(checked) and all(record['status'] == 'active' for record in checked)
    return {
        'schema_version': 1,
        'scope': 'static_saved_instrument_slot_activation_only',
        'project': str(Path(project).resolve()),
        'plugin_executed': False,
        'supported_plugin_uids': sorted(allowed_uids),
        'selection': 'explicit_instrument_track_indices' if wanted else 'recognized_plugin_uids_only',
        'result': 'all_selected_active' if ok else 'inactive_or_unresolved',
        'checked': checked,
        'skipped': skipped,
        'limitation': 'No sample, routing, audio or Cubase playback verification',
    }, 0 if ok else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--track', action='append', type=positive_index, default=[],
                        help='1-based instrument-track index; repeat for intended audible instances')
    parser.add_argument('--plugin-uid', action='append', type=uid_argument,
                        help='Explicitly confirmed UID; when supplied, replaces the observed default')
    parser.add_argument('--out', type=Path, help='New private JSON report; existing files are never replaced')
    args = parser.parse_args()
    try:
        if args.out is not None and args.out.exists():
            raise FileExistsError('Report already exists: ' + str(args.out))
        report, code = inspect_project(args.project, args.track,
                                       set(args.plugin_uid or [OBSERVED_UID]))
        output = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
        if args.out is not None:
            with args.out.open('x', encoding='utf-8') as stream:
                stream.write(output)
        print(output, end='')
        return code
    except (OSError, ValueError, KeyError, UnicodeError, TypeError, AttributeError,
            IndexError, struct.error) as error:
        print(json.dumps({'scope': 'static_saved_instrument_slot_activation_only',
                          'error': str(error), 'plugin_executed': False}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

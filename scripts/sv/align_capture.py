"""Align a process recording to two or more known synchronization markers.

Requires numpy and soundfile. Marker values are project-time seconds in the
reference WAV: --marker START:DURATION. Reserve the --clear-before interval
for synchronization only; this script cannot determine whether it contains
intentional vocals. Output is 32-bit float WAV, suitable for later mixing.
The reference WAV and captured WAV must have the same sample rate.
Container length alone does not prove uninterrupted voice synthesis: also read
the recorder sidecar for early exit, padding, gaps and timestamp errors, and
check the actual sung intervals. This helper does not infer vocal completeness.
"""
from pathlib import Path
import argparse
import json
import math
import numpy as np
import soundfile as sf


def marker_value(value):
    try:
        start, length = map(float, value.split(':'))
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Use START:DURATION in seconds') from exc
    if not all(map(math.isfinite, (start, length))) or start < 0 or length <= 0:
        raise argparse.ArgumentTypeError('Marker start must be >= 0 and duration > 0')
    return start, length


def correlation(x, template, minimum_rms):
    if len(x) < len(template):
        raise ValueError('Search interval is shorter than a synchronization marker')
    template_energy = float(np.dot(template, template))
    if template_energy < len(template) * minimum_rms**2:
        raise ValueError('Reference marker is silent or too quiet')
    size = 1 << (len(x) + len(template) - 2).bit_length()
    convolution = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(template[::-1], size), size)
    dots = convolution[len(template)-1:len(x)]
    cumulative = np.concatenate(([0.], np.cumsum(x*x, dtype=np.float64)))
    energy = np.maximum(cumulative[len(template):] - cumulative[:-len(template)], 0)
    scores = dots / np.sqrt(np.maximum(energy * template_energy, 1e-24))
    # Roundoff in an almost-silent window can otherwise produce a false high
    # normalized score even though there is no actual synchronization signal.
    scores[energy < len(template) * minimum_rms**2] = 0
    return scores


def align(capture, reference, output, *, markers, duration, clear_before,
          search_seconds=60., minimum_score=.75, minimum_rms=.001, tolerance_ms=1.):
    capture, reference, output = map(Path, (capture, reference, output))
    if output.exists() or Path(str(output)+'.json').exists():
        raise FileExistsError('Choose new output and sidecar paths')
    values = (duration, clear_before, search_seconds, minimum_score, minimum_rms, tolerance_ms)
    if not all(map(math.isfinite, values)) or duration <= 0 or search_seconds <= 0:
        raise ValueError('Timing and threshold values must be finite; duration/search must be positive')
    if not 0 < minimum_score <= 1 or minimum_rms <= 0 or tolerance_ms < 0:
        raise ValueError('Invalid synchronization thresholds')
    if len(markers) < 2:
        raise ValueError('Use at least two distinct synchronization markers')
    markers = sorted(markers)
    if any(a + length > b for (a, length), (b, _) in zip(markers, markers[1:])):
        raise ValueError('Reference marker intervals must not overlap')
    if not max(a+b for a, b in markers) <= clear_before <= duration:
        raise ValueError('clear-before must cover every marker and remain within output duration')
    audio, sr = sf.read(capture, dtype='float32', always_2d=True)
    sync, sync_sr = sf.read(reference, dtype='float64', always_2d=True)
    if sr != sync_sr:
        raise ValueError(f'Sample rates differ: capture={sr}, reference={sync_sr}')
    if not np.isfinite(audio).all() or not np.isfinite(sync).all():
        raise ValueError('Nonfinite samples in capture or reference')
    x = audio[:min(len(audio), round(search_seconds*sr))].mean(axis=1, dtype=np.float64)
    offsets, scores_found = [], []
    for onset, length in markers:
        first, last = round(onset*sr), round((onset+length)*sr)
        if first < 0 or last > len(sync) or last <= first:
            raise ValueError('Marker interval falls outside reference WAV')
        template = sync[first:last].mean(axis=1)
        scores = correlation(x, template, minimum_rms)
        index = int(np.argmax(scores))
        score = float(scores[index])
        if score < minimum_score:
            raise ValueError(f'No reliable marker at project time {onset}: score={score:.4f}')
        offsets.append(index-first)
        scores_found.append(score)
    if max(offsets)-min(offsets) > round(sr*tolerance_ms/1000):
        raise ValueError(f'Synchronization markers disagree: {offsets}')
    offset = round(sum(offsets)/len(offsets))
    count = round(duration*sr)
    if offset < 0 or offset+count > len(audio):
        raise ValueError('Capture does not contain the entire requested project interval; record again')
    result = audio[offset:offset+count].copy()
    result[:round(clear_before*sr)] = 0
    sf.write(output, result, sr, subtype='FLOAT')
    report = {'source':str(capture), 'reference':str(reference), 'output':str(output),
        'sample_rate':sr, 'recorded_seconds':len(audio)/sr, 'output_seconds':count/sr,
        'project_zero_frame':offset, 'sync_scores':scores_found, 'sync_offsets':offsets,
        'cleared_seconds':clear_before, 'length_check_is_container_only':True,
        'peak':float(np.max(np.abs(result))),
        'rms':float(np.sqrt(np.mean(result.astype(np.float64)**2)))}
    Path(str(output)+'.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('reference', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--marker', type=marker_value, action='append', required=True)
    parser.add_argument('--duration', type=float, required=True)
    parser.add_argument('--clear-before', type=float, required=True)
    parser.add_argument('--search-seconds', type=float, default=60.)
    parser.add_argument('--minimum-score', type=float, default=.75)
    parser.add_argument('--minimum-rms', type=float, default=.001)
    parser.add_argument('--tolerance-ms', type=float, default=1.)
    args = vars(parser.parse_args())
    args['markers'] = args.pop('marker')
    print(json.dumps(align(**args), indent=2))


if __name__ == '__main__':
    main()

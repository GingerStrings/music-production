"""Create two distinguishable chirps in an otherwise silent reference WAV.

The default 2.25-second file has 60 ms markers at project seconds 0.5 and 1.5.
Place this audio at project zero in a dedicated temporary track, reserving the
whole reference interval outside vocals, and remove it from final deliverables.
Requires numpy and soundfile. This utility does not edit an SV project.
"""
from pathlib import Path
import argparse
import json
import math
import numpy as np
import soundfile as sf


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--sample-rate', type=int, default=48000)
    p.add_argument('--first', type=float, default=.5)
    p.add_argument('--second', type=float, default=1.5)
    p.add_argument('--marker-duration', type=float, default=.06)
    p.add_argument('--duration', type=float, default=2.25)
    args = p.parse_args()
    if args.output.exists() or args.output.with_suffix('.json').exists():
        p.error('Choose new output and sidecar paths')
    numbers = (args.first, args.second, args.marker_duration, args.duration)
    if not all(map(math.isfinite, numbers)) or args.sample_rate < 8000 or args.marker_duration <= 0:
        p.error('Use finite timing values, positive marker length and a sample rate of at least 8000 Hz')
    if not (0 <= args.first < args.first+args.marker_duration <= args.second
            < args.second+args.marker_duration <= args.duration):
        p.error('Markers must fit inside the reference and not overlap')
    signal = np.zeros((round(args.duration*args.sample_rate), 2), np.float32)
    count = round(args.marker_duration*args.sample_rate)
    if count < 8:
        p.error('Marker must contain at least eight samples')
    t = np.arange(count)/args.sample_rate
    for start, low, high in [(args.first, 1200, 2400), (args.second, 2100, 800)]:
        chirp = .18*np.hanning(count)*np.sin(2*np.pi*(low*t+(high-low)*t*t/(2*args.marker_duration)))
        index = round(start*args.sample_rate)
        if index+count > len(signal):
            p.error('Rounded marker interval exceeds reference length')
        signal[index:index+count] = chirp[:, None]
    sf.write(args.output, signal, args.sample_rate, subtype='PCM_24')
    metadata = {'sample_rate':args.sample_rate, 'duration_seconds':len(signal)/args.sample_rate,
        'markers':[{'start':n, 'duration':args.marker_duration} for n in (args.first, args.second)],
        'purpose':'Temporary recording alignment signal; remove before delivery'}
    args.output.with_suffix('.json').write_text(json.dumps(metadata, indent=2), encoding='utf8')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()

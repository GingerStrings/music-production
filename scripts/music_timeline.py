"""Quarter-note timelines with step tempo and linear-BPM ramps. No DAW needed."""
import bisect
import math


def number(value, name, low=0, high=10_000_000):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'Invalid {name}: {value!r}')
    return value


class TempoMap:
    """A point's curve describes the segment arriving at that point.

    `step` holds the previous BPM until this point; `linear` interpolates BPM
    against musical beats. Seconds are the integral of 60/BPM, not average BPM.
    """
    def __init__(self, points):
        if not isinstance(points, list) or not 1 <= len(points) <= 100_000:
            raise ValueError('Expected a nonempty tempo_map')
        self.points = []
        for point in points:
            if set(point) != {'beat', 'bpm', 'curve'}:
                raise ValueError('Tempo points require beat, bpm, curve')
            beat = number(point['beat'], 'tempo beat')
            bpm = number(point['bpm'], 'BPM', 1, 1000)
            if point['curve'] not in ('step', 'linear'):
                raise ValueError('Unknown tempo curve')
            if self.points and beat <= self.points[-1]['beat']:
                raise ValueError('Tempo beats must increase strictly')
            self.points.append(dict(beat=beat, bpm=bpm, curve=point['curve']))
        if self.points[0]['beat'] != 0 or self.points[0]['curve'] != 'step':
            raise ValueError('Tempo map must start with a step at beat zero')
        self.beats = [p['beat'] for p in self.points]
        self.seconds = [0.]
        for i in range(len(self.points)-1):
            self.seconds.append(self.seconds[-1] + self._seconds(i, self.beats[i+1]-self.beats[i]))

    def _slope(self, i):
        if i+1 >= len(self.points) or self.points[i+1]['curve'] == 'step':
            return 0.
        return (self.points[i+1]['bpm']-self.points[i]['bpm']) / (self.beats[i+1]-self.beats[i])

    def _seconds(self, i, beats):
        bpm, slope = self.points[i]['bpm'], self._slope(i)
        if abs(slope) < 1e-12:
            return beats*60/bpm
        return 60*math.log1p(slope*beats/bpm)/slope

    def beat_to_seconds(self, beat):
        number(beat, 'beat')
        i = max(0, bisect.bisect_right(self.beats, beat)-1)
        return self.seconds[i] + self._seconds(i, beat-self.beats[i])

    def seconds_to_beat(self, seconds):
        number(seconds, 'seconds', 0, 1e12)
        i = max(0, bisect.bisect_right(self.seconds, seconds)-1)
        delta, bpm, slope = seconds-self.seconds[i], self.points[i]['bpm'], self._slope(i)
        beats = delta*bpm/60 if abs(slope) < 1e-12 else bpm*math.expm1(delta*slope/60)/slope
        return self.beats[i]+beats

    def advance(self, beat, milliseconds):
        number(milliseconds, 'advance milliseconds', -10000, 10000)
        number(beat, 'beat')
        if milliseconds == 0:return beat
        seconds = self.beat_to_seconds(beat)-milliseconds/1000
        if seconds < -1e-12:
            raise ValueError('Insufficient preroll for timing advance')
        return self.seconds_to_beat(max(0, seconds))


def validate_meters(points):
    """Return zero-based bar positions; changes must lie at bar boundaries."""
    if not isinstance(points, list) or not 1 <= len(points) <= 100_000:
        raise ValueError('Expected a nonempty meter_map')
    result = []
    for p in points:
        if set(p) != {'beat', 'numerator', 'denominator'}:
            raise ValueError('Meter points require beat, numerator, denominator')
        beat = number(p['beat'], 'meter beat')
        n, d = p['numerator'], p['denominator']
        if type(n) is not int or not 1 <= n <= 64 or type(d) is not int or d not in (1, 2, 4, 8, 16, 32, 64):
            raise ValueError('Invalid time signature')
        bar = 0
        if result:
            last = result[-1]
            bars = (beat-last['beat']) / (last['numerator']*4/last['denominator'])
            if bars <= 0 or abs(bars-round(bars)) > 1e-8:
                raise ValueError('Time signature changes must lie on bar boundaries')
            bar = last['bar']+round(bars)
        elif beat != 0:
            raise ValueError('Meter map must start at beat zero')
        result.append(dict(p, bar=bar))
    return result

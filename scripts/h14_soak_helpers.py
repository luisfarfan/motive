"""Bounded offline statistics for controlled H14 media; no processes or files."""
from array import array
from collections import Counter
import bisect
import hashlib
import math
import statistics
import sys


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return None
    return {'count': len(ordered), 'min': ordered[0], 'median': statistics.median(ordered),
            'p95': ordered[math.ceil(.95 * len(ordered)) - 1], 'max': ordered[-1]}


class Timeline:
    def __init__(self, gap_limit):
        self.limit = gap_limit
        self.count = self.missing = self.non_increasing = self.gaps = 0
        self.first = self.last = self.min_gap = self.max_gap = None
        self.examples = []

    def add(self, value):
        self.count += 1
        if value in (None, 'N/A', ''):
            self.missing += 1
            return
        value = float(value)
        if not math.isfinite(value):
            raise ValueError('Non-finite timestamp')
        if self.first is None:
            self.first = value
        if self.last is not None:
            gap = value - self.last
            self.min_gap = gap if self.min_gap is None else min(gap, self.min_gap)
            self.max_gap = gap if self.max_gap is None else max(gap, self.max_gap)
            self.non_increasing += gap <= 0
            self.gaps += gap > self.limit
            if (gap <= 0 or gap > self.limit) and len(self.examples) < 32:
                self.examples.append({'index': self.count - 1, 'gap_s': gap})
        self.last = value

    def result(self):
        return {'count': self.count, 'missing': self.missing, 'first_s': self.first,
                'last_s': self.last, 'min_gap_s': self.min_gap, 'max_gap_s': self.max_gap,
                'non_increasing': self.non_increasing, 'gap_limit_s': self.limit,
                'gaps_over_limit': self.gaps, 'examples_first32': self.examples}


class HashRuns:
    """Duration includes the final frame interval; duplicates are not dropped."""
    def __init__(self):
        self.count = self.changes = self.run_frames = 0
        self.key = self.first = self.last = self.duration = None
        self.maximum = {'frames': 0, 'seconds': 0., 'first_pts_s': None, 'last_pts_s': None}
        self.lengths = Counter()

    def _close_run(self):
        if not self.run_frames:
            return
        seconds = self.last + self.duration - self.first
        self.lengths[self.run_frames] += 1
        if seconds > self.maximum['seconds']:
            self.maximum = {'frames': self.run_frames, 'seconds': seconds,
                            'first_pts_s': self.first, 'last_pts_s': self.last}

    def add(self, key, pts, duration):
        if duration <= 0 or not math.isfinite(pts + duration):
            raise ValueError('Invalid frame time')
        if self.last is not None and pts <= self.last:
            raise ValueError('Non-increasing frame time')
        if self.count and key != self.key:
            self._close_run()
            self.changes += 1
            self.run_frames = 0
        if not self.run_frames:
            self.first = pts
        self.count += 1
        self.run_frames += 1
        self.key, self.last, self.duration = key, pts, duration

    def finish(self):
        self._close_run()
        return {'frames': self.count, 'changing_pairs': self.changes,
                'duplicate_pairs': max(0, self.count - 1 - self.changes),
                'longest_constant_run': self.maximum,
                'run_length_histogram': dict(sorted(self.lengths.items()))}


class QuadrantFreshness:
    WIDTH, HEIGHT = 128, 72
    MAD_THRESHOLD = 1.0
    CHANGED_PIXEL_DELTA = 8
    CHANGED_FRACTION_THRESHOLD = .02

    def __init__(self):
        self.exact = [HashRuns() for _ in range(4)]
        self.meaningful = [HashRuns() for _ in range(4)]
        self.anchors = [None] * 4
        self.generations = [0] * 4
        self.indices = tuple(y * 64 + x for y in range(2, 36, 4) for x in range(2, 64, 4))

    def add(self, frame, pts, duration):
        if len(frame) != self.WIDTH * self.HEIGHT:
            raise ValueError('Incomplete gray frame')
        result = {'full_md5': hashlib.md5(frame).hexdigest(), 'quadrants': []}
        for index in range(4):
            x, y = (index % 2) * 64, (index // 2) * 36
            pixels = b''.join(frame[(y + row) * 128 + x:(y + row) * 128 + x + 64] for row in range(36))
            digest = hashlib.md5(pixels).hexdigest()
            self.exact[index].add(digest, pts, duration)
            anchor = self.anchors[index]
            if anchor is None:
                mad = fraction = 0.
                self.anchors[index] = pixels
            else:
                deltas = [abs(pixels[position] - anchor[position]) for position in self.indices]
                mad = sum(deltas) / len(deltas)
                fraction = sum(value >= self.CHANGED_PIXEL_DELTA for value in deltas) / len(deltas)
                if mad >= self.MAD_THRESHOLD and fraction >= self.CHANGED_FRACTION_THRESHOLD:
                    self.generations[index] += 1
                    self.anchors[index] = pixels
            self.meaningful[index].add(self.generations[index], pts, duration)
            result['quadrants'].append({'md5': digest, 'mad_from_reference': mad,
                                       'changed_probe_fraction': fraction})
        return result

    def finish(self):
        return {'gray_size': [128, 72], 'quadrant_size': [64, 36],
                'probe_pixels_per_quadrant': len(self.indices),
                'meaningful_change': {'mad_min': self.MAD_THRESHOLD,
                    'pixel_delta_min': self.CHANGED_PIXEL_DELTA,
                    'changed_probe_fraction_min': self.CHANGED_FRACTION_THRESHOLD,
                    'reference': 'last meaningful-change frame; not merely previous frame'},
                'quadrants': [{'index': i, 'exact': self.exact[i].finish(),
                               'meaningful': self.meaningful[i].finish()} for i in range(4)]}


def tone_amplitude(values, frequency, sample_rate):
    coefficient = 2 * math.cos(2 * math.pi * frequency / sample_rate)
    first = second = 0.
    for value in values:
        next_value = value + coefficient * first - second
        second, first = first, next_value
    power = max(0., first * first + second * second - coefficient * first * second)
    return 2 * math.sqrt(power) / len(values)


def packet_origin_proof(trace, first_packets, tolerance=.0011):
    result = {'status': 'INCONCLUSIVE', 'kinds': {}, 'tolerance_s': tolerance,
              'limit': 'Metadata correspondence, not cryptographic packet identity or encoder-to-observer delivery'}
    summary = trace['summary']
    records = trace['packets']
    sequences = [packet['sequence'] for packet in records]
    if (trace['snapshot_busy'] or summary['trace_missed_records'] or summary['trace_overwritten_records']
            or not sequences or sequences != list(range(1, len(sequences) + 1))):
        result['reason'] = 'incomplete_initial_trace'
        return result
    for kind in ('video', 'audio'):
        native = [packet for packet in records if packet['media_type'] == kind]
        actual = first_packets[kind]
        count = min(3, len(native), len(actual))
        row = {'compared_packets': count, 'status': 'INCONCLUSIVE', 'comparisons': []}
        result['kinds'][kind] = row
        if count < 3:
            row['reason'] = 'at_least_three_initial_packets_required'
            continue
        origin = float(actual[0]['pts_time']) - native[0]['pts'] * native[0]['timebase_num'] / native[0]['timebase_den']
        row['origin_offset_s'] = origin
        for before, after in zip(native[:count], actual[:count]):
            expected = before['pts'] * before['timebase_num'] / before['timebase_den'] + origin
            row['comparisons'].append({'native_sequence': before['sequence'],
                'size_equal': before['size'] == int(after['size']),
                'keyframe_equal': bool(before['keyframe']) == ('K' in after['flags']),
                'pts_delta_s': float(after['pts_time']) - expected})
        row['status'] = 'MATCHED_METADATA_PREFIX' if all(
            item['size_equal'] and item['keyframe_equal'] and abs(item['pts_delta_s']) <= tolerance
            for item in row['comparisons']) else 'INCONCLUSIVE'
    if all(row['status'] == 'MATCHED_METADATA_PREFIX' for row in result['kinds'].values()):
        result['status'] = 'MATCHED_METADATA_PREFIX'
    return result


def tail_candidates(initial, final, first_packets, pts_by_kind, tolerance=.0011):
    """Keep first actual PTS and exact nearest neighbors, including duplicates."""
    retained, counts = [], []
    for kind in ('video', 'audio'):
        pts = sorted(pts_by_kind[kind])
        native_first = next(packet for packet in initial['packets'] if packet['media_type'] == kind)
        first = first_packets[kind][0]
        retained.append(first)
        origin = float(first['pts_time']) - native_first['pts'] * native_first['timebase_num'] / native_first['timebase_den']
        indices = set()
        for packet in (p for p in final['packets'] if p['media_type'] == kind):
            expected = packet['pts'] * packet['timebase_num'] / packet['timebase_den'] + origin
            lo, hi = bisect.bisect_left(pts, expected - tolerance), bisect.bisect_right(pts, expected + tolerance)
            indices.update(range(lo, hi))
            nearest = bisect.bisect_left(pts, expected)
            indices.update(i for i in (nearest - 1, nearest) if 0 <= i < len(pts))
            counts.append({'kind': kind, 'native_sequence': packet['sequence'],
                           'expected_pts_s': expected, 'candidates_within_tolerance': hi - lo})
        # The first packet above establishes origin; avoid adding its same index
        # twice, while retaining other packets with duplicate timestamps.
        first_index = bisect.bisect_left(pts, float(first['pts_time']))
        indices.discard(first_index)
        retained.extend({'codec_type': kind, 'pts_time': repr(pts[index])} for index in sorted(indices))
    return retained, counts


class PCMStats:
    """Stereo f32le, 100 ms windows, at most one selected second retained."""
    def __init__(self, window_sink, tone_sink, tone_seconds=(), sample_rate=48000):
        self.sample_rate = sample_rate
        self.window_frames = sample_rate // 10
        self.window_bytes = self.window_frames * 2 * 4
        self.window_sink, self.tone_sink = window_sink, tone_sink
        self.tone_seconds = set(tone_seconds)
        self.buffer = bytearray()
        self.frames = self.windows = self.partial_windows = 0
        self.squares, self.peaks, self.clipped, self.nonfinite = [0.] * 2, [0.] * 2, [0] * 2, [0] * 2
        self.rms_windows = [[], []]
        self.silent_windows, self.silent_run, self.longest_silence = [0] * 2, [0] * 2, [0] * 2
        self.tone_samples = [array('f'), array('f')]
        self.tones = []

    def _window(self, block):
        samples = array('f', block)
        if sys.byteorder != 'little':
            samples.byteswap()
        if len(samples) % 2:
            raise ValueError('Incomplete stereo sample')
        count = len(samples) // 2
        full = count == self.window_frames
        second = self.frames // self.sample_rate
        row = {'first_frame': self.frames, 'offset_seconds': self.frames / self.sample_rate,
               'frames': count, 'full_100ms_window': full, 'channels': []}
        for channel in range(2):
            values = samples[channel::2]
            square = peak = 0.
            clipped = nonfinite = 0
            for value in values:
                if not math.isfinite(value):
                    nonfinite += 1
                    continue
                square += value * value
                peak = max(peak, abs(value))
                clipped += abs(value) >= .999
            rms = math.sqrt(square / count)
            self.squares[channel] += square
            self.peaks[channel] = max(self.peaks[channel], peak)
            self.clipped[channel] += clipped
            self.nonfinite[channel] += nonfinite
            if full:
                self.rms_windows[channel].append(rms)
                silent = rms < 1e-4
                self.silent_windows[channel] += silent
                self.silent_run[channel] = self.silent_run[channel] + 1 if silent else 0
                self.longest_silence[channel] = max(self.longest_silence[channel], self.silent_run[channel])
            row['channels'].append({'rms': rms, 'peak': peak, 'samples_abs_ge_0_999': clipped,
                                    'nonfinite_samples': nonfinite})
            if second in self.tone_seconds:
                self.tone_samples[channel].extend(value if math.isfinite(value) else 0. for value in values)
        self.frames += count
        self.windows += full
        self.partial_windows += not full
        self.window_sink(row)
        if second in self.tone_seconds and len(self.tone_samples[0]) == self.sample_rate:
            tone = {'first_frame': second * self.sample_rate, 'offset_seconds': second,
                    'frames': self.sample_rate, 'channels': []}
            for values in self.tone_samples:
                tone['channels'].append({str(hz): tone_amplitude(values, hz, self.sample_rate)
                                         for hz in (440, 997, 2011)})
            self.tones.append(tone)
            self.tone_sink(tone)
            self.tone_samples = [array('f'), array('f')]

    def feed(self, block):
        self.buffer.extend(block)
        while len(self.buffer) >= self.window_bytes:
            self._window(bytes(self.buffer[:self.window_bytes]))
            del self.buffer[:self.window_bytes]

    def finish(self):
        if len(self.buffer) % 8:
            raise ValueError('Truncated stereo f32le data')
        if self.buffer:
            self._window(bytes(self.buffer))
            self.buffer.clear()
        return {'sample_rate': self.sample_rate, 'channels': 2, 'frames_per_channel': self.frames,
                'duration_seconds': self.frames / self.sample_rate, 'windows_100ms': self.windows,
                'partial_windows': self.partial_windows, 'tone_windows': self.tones,
                'channel_statistics': [{'rms': math.sqrt(self.squares[i] / self.frames) if self.frames else None,
                    'peak': self.peaks[i], 'samples_abs_ge_0_999': self.clipped[i],
                    'nonfinite_samples': self.nonfinite[i], 'window_rms': distribution(self.rms_windows[i]),
                    'full_windows_below_minus80_dbfs': self.silent_windows[i],
                    'longest_below_minus80_dbfs_seconds': self.longest_silence[i] / 10} for i in range(2)],
                'timing': 'decoded sample offsets; no A/V origin or synchronization inference'}

"""Pure identity, geometry and counter checks for the owned collection fixture."""
import math
import pathlib

PHASES = ('fixture_front', 'studio_front', 'fixture_return')
PROFILE_ID_PREFIX = 'h14-collection-'
PROFILE_ID_MAX_LENGTH = 48  # src/output.rs::OutputProfile::validate, ASCII bytes.


def require(condition, message):
    if not condition:
        raise ValueError(message)


def collection_profile_id(trial_id):
    require(isinstance(trial_id, str) and trial_id.isascii()
            and 1 <= len(trial_id) <= PROFILE_ID_MAX_LENGTH-len(PROFILE_ID_PREFIX),
            'Trial ID must fit the 48-byte composed output profile ID')
    require(all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in trial_id)
            and any(c in 'abcdefghijklmnopqrstuvwxyz0123456789' for c in trial_id),
            'Trial ID requires lowercase ASCII letters/digits with optional hyphens/underscores')
    return PROFILE_ID_PREFIX + trial_id


def validate_manifest(value):
    require(isinstance(value, dict) and set(value) == {'version', 'trial_id', 'arm', 'seconds', 'owner', 'fixture',
                          'markers', 'receiver_ffmpeg'}, 'Unexpected manifest fields')
    require(type(value['version']) is int and value['version'] == 1
            and value['arm'] in ('default', 'join-all'), 'Unsupported arm/version')
    collection_profile_id(value['trial_id'])
    require(type(value['seconds']) is int and 45 <= value['seconds'] <= 180, 'Trial must last 45–180 seconds')
    require(set(value['owner']) == {'bundle', 'pid'}, 'Unexpected owner fields')
    require(set(value['fixture']) == {'bundle', 'pid', 'window_id', 'log', 'build_manifest'},
            'Unexpected fixture fields')
    for key in ('owner', 'fixture'):
        require(type(value[key]['pid']) is int and value[key]['pid'] > 0, 'Positive exact PID required')
    require(value['owner']['pid'] != value['fixture']['pid'], 'Separate owner and fixture required')
    require(type(value['fixture']['window_id']) is int and 0 < value['fixture']['window_id'] <= 0xffffffff,
            'Positive observed window ID required')
    paths = [value['owner']['bundle'], value['fixture']['bundle'], value['fixture']['log'],
             value['fixture']['build_manifest'], value['markers'], value['receiver_ffmpeg']]
    require(all(isinstance(path, str) and '\0' not in path and pathlib.Path(path).is_absolute()
                for path in paths), 'Explicit absolute local paths are required')
    return value


def validate_media_duration(duration, manifest):
    # Preserve the original 60s trial +30s decode allowance. Longer CUA
    # observation changes only this work bound, never audiovisual acceptance.
    validate_manifest(manifest)
    limit = min(manifest['seconds'] + 30, 210)
    require(type(duration) in (int, float) and math.isfinite(duration)
            and 0 < duration <= limit, 'Bounded trial media duration required')
    return limit


def validate_fixture(events, manifest):
    fixture = manifest['fixture']
    require(1 <= len(events) <= 2048, 'Bounded fresh fixture log required')
    for event in events:
        require(event.get('event') in ('ready', 'window_state'), 'Unknown fixture event')
        require(event.get('pid') == fixture['pid'] and event.get('window_id') == fixture['window_id']
                and event.get('arm') == manifest['arm'], 'Fixture log identity changed')
    ready = [event for event in events if event['event'] == 'ready']
    require(len(ready) == 1 and ready[0]['bundle_id'] == 'local.motive.collectionfixture',
            'Exactly one ready event from this fresh fixture is required')
    require(ready[0]['counter'] == {'bits': 16, 'least_significant_bit': 'left', 'x': 24, 'y': 24,
                                   'step_points': 36, 'width_points': 30, 'height_points': 48,
                                   'coordinate_origin': 'bottom_left'}, 'Unknown counter geometry')
    require(ready[0]['audio'] is False and ready[0]['capture'] is False, 'Fixture must be video stimulus only')
    require(ready[0]['content_hz'] == 10 and ready[0]['draw_request_hz'] == 30
            and ready[0]['offscreen_snapshots'] is False and ready[0]['global_preferences_changed'] is False,
            'Unexpected fixture clock or side effects')
    states = [event for event in events if event['event'] == 'window_state']
    require(states and all(event['window_class'] == 'NSWindow' and event['window_level'] == 0
                           for event in states), 'Fixture class/level changed')
    # AppKit NSWindow.h: Primary=1<<16, Auxiliary=1<<17,
    # CanJoinAllApplications=1<<18. Only this exclusive group may change.
    exclusive = (1 << 16) | (1 << 17) | (1 << 18)
    for event in states:
        initial = event['initial_collection_behavior']
        expected = initial if manifest['arm'] == 'default' else (initial & ~exclusive) | (1 << 18)
        require(event['collection_behavior'] == expected, 'Unexpected collectionBehavior change')
    return ready[0], states


def validate_markers(events, manifest, complete=False):
    require(len(events) <= 3, 'Only three focus observation markers are accepted')
    for index, event in enumerate(events):
        require(event.get('trial_id') == manifest['trial_id'] and event.get('owner_pid') == manifest['owner']['pid']
                and event.get('fixture_pid') == manifest['fixture']['pid']
                and event.get('window_id') == manifest['fixture']['window_id'], 'Marker identity changed')
        require(event.get('phase') == PHASES[index] and event.get('clock') == 'python.time.monotonic',
                'Markers must be fixture → studio → fixture, using the named host clock')
        if event.get('observation') == 'system_frontmost_application':
            from h15_focus import corroborate
            expected = manifest['owner']['pid'] if event['phase'] == 'studio_front' else manifest['fixture']['pid']
            check = corroborate(event['system_probe'], event['fixture_observation'],
                                fixture_pid=manifest['fixture']['pid'],
                                window_id=manifest['fixture']['window_id'], expected_pid=expected)
            require(check['status'] == 'PASS', 'Independent system focus is not corroborated')
            anchor = event['clock_anchor']
            require(anchor['fixture_clock'] == 'NSProcessInfo.systemUptime'
                    and anchor['host_clock'] == 'python.time.monotonic'
                    and 0 <= anchor['fixture_clock_s']-event['system_probe']['after_s'] <= 1.5
                    and 0 <= anchor['host_before_s']-event['host_monotonic'] <= 1.5,
                    'Independent focus marker is stale or uses another clock')
        else:
            require(event.get('observation') == 'root_observed_focus_after_cua', 'Focus must be observed by root')
        require(math.isfinite(event['host_monotonic']) and math.isfinite(event['wall_unix']), 'Invalid marker clock')
        if index:
            require(event['host_monotonic'] > events[index-1]['host_monotonic'], 'Markers must advance')
    if complete:
        require(len(events) == 3, 'All three root focus markers are required')
    return events


def counter_patches(source_size, window_points, output_size=(480, 270)):
    """OBS SCALE_INNER centered in full canvas; fixture bottom aligns to window bottom."""
    width, height = source_size
    ww, wh = window_points
    require(min(width, height, ww, wh) > 0, 'Missing source/window geometry')
    if abs(width / height - ww / wh) >= .015:
        # The fixture content is exactly 680x240 points. Accept content-only
        # capture only when its measured aspect proves that model; never hunt
        # arbitrary crops to make a static image look like a counter.
        require(ww == 680 and abs(width / height - 680 / 240) < .015,
                'Capture aspect differs from owned window/content; geometry unverified')
        wh = 240
    ow, oh = output_size
    scale = min(ow / width, oh / height)
    x0, y0 = (ow-width*scale)/2, (oh-height*scale)/2
    sx, sy = width*scale/ww, height*scale/wh
    boxes = []
    for bit in range(16):
        cx, cy = x0+(24+36*bit+15)*sx, y0+(wh-48)*sy
        radius = max(1, int(min(30*sx, 48*sy)/5))
        box = (int(cx)-radius, int(cy)-radius, int(cx)+radius+1, int(cy)+radius+1)
        require(0 <= box[0] < box[2] <= ow and 0 <= box[1] < box[3] <= oh, 'Counter ROI outside decoded frame')
        boxes.append(box)
    return boxes


def decode_counter(gray, width, boxes):
    values = []
    for left, top, right, bottom in boxes:
        pixels = [gray[y*width+x] for y in range(top, bottom) for x in range(left, right)]
        mean = sum(pixels)/len(pixels)
        if not (mean <= 12 or mean >= 190):
            return None
        values.append(int(mean >= 190))
    # The 6-point gaps retain the fixture's dark-blue background. This rejects
    # a uniform black output while allowing real all-zero/all-one bit patterns.
    for a, b in zip(boxes, boxes[1:]):
        x = int(((a[0]+a[2]-1)/2 + (b[0]+b[2]-1)/2)/2)
        y = (a[1]+a[3]-1)//2
        if not 20 <= gray[y*width+x] <= 120:
            return None
    return sum(value << bit for bit, value in enumerate(values))


def counter_summary(rows):
    valid = [row for row in rows if row['counter'] is not None]
    if len(valid) < 5:
        return {'status': 'INCONCLUSIVE', 'reason': 'insufficient_decodable_counter_frames'}
    stalls, jumps, decode_gaps = [], [], []
    start = valid[0]
    advanced = 0
    for previous, current in zip(valid, valid[1:]):
        delta = (current['counter']-previous['counter']) % 65536
        if delta:
            stalls.append(previous['pts_s']-start['pts_s'])
            if delta > 100:
                jumps.append({'pts_s': current['pts_s'], 'ticks': delta})
            advanced += delta
            start = current
        if current['pts_s']-previous['pts_s'] > .5:
            decode_gaps.append({'pts_s': current['pts_s'], 'gap_s': current['pts_s']-previous['pts_s']})
    stalls.append(valid[-1]['pts_s']-start['pts_s'])
    span = valid[-1]['pts_s']-valid[0]['pts_s']
    invalid = len(rows)-len(valid)
    return {'status': 'FAIL' if max(stalls) >= 1.0 or jumps or advanced == 0 else
            'INCONCLUSIVE' if invalid > len(rows)*.05 or decode_gaps or span < 5 else 'PASS',
            'frames': len(rows), 'decodable_frames': len(valid), 'invalid_frames': invalid,
            'span_s': span, 'advanced_ticks': advanced, 'longest_repeated_counter_s': max(stalls),
            'tick_jumps': jumps, 'decode_gaps': decode_gaps}


def focus_conditions(events, anchors, markers, trial_end):
    """Corroborate root's focus observations; never infer published pixels.

    Fixture uptime is mapped through measured Foundation/host brackets. No
    subtraction involving CLOCK_MONOTONIC_RAW or an assumed shared epoch.
    """
    result = {'status': 'NOT_OBSERVED', 'phases': {},
              'basis': 'Validated focus markers plus contemporaneous exact fixture metadata; marker observation identifies CUA or independent system PID.',
              'limits': ['app_active/occlusion are metadata, not proof of visible or captured pixels.',
                         'Fixture inactivity corroborates the studio marker; it alone does not identify the frontmost app.']}
    try:
        require(anchors and len(markers) == 3, 'Complete focus markers and clock anchors required')
        offsets = []
        for anchor in anchors:
            require(anchor['fixture_clock'] == 'NSProcessInfo.systemUptime'
                    and anchor['host_clock'] == 'python.time.monotonic', 'Unknown fixture/host clock pair')
            before, after, uptime = anchor['host_before_s'], anchor['host_after_s'], anchor['fixture_clock_s']
            require(all(type(x) in (int, float) and math.isfinite(x) for x in (before, after, uptime))
                    and 0 <= after-before <= 1, 'Invalid clock anchor bracket')
            offsets.append((before-uptime, after-uptime))
        lo, hi = min(x[0] for x in offsets), max(x[1] for x in offsets)
        require(0 <= hi-lo <= 1, 'Clock offset changed or uncertainty exceeded one second')
        boundaries = [m['host_monotonic'] for m in markers]+[trial_end]
        require(all(type(x) in (int, float) and math.isfinite(x) for x in boundaries)
                and all(a < b for a, b in zip(boundaries, boundaries[1:])), 'Invalid focus interval')
        result['clock_mapping'] = {'offset_interval_s': [lo, hi], 'uncertainty_s': hi-lo,
                                   'boundary_guard_s': 2, 'method': 'Envelope of measured same-API clock brackets'}
        states = [event for event in events if event.get('event') == 'window_state']
        fields = ('app_active', 'key_window', 'window_visible', 'window_occlusion_visible',
                  'on_active_space', 'app_hidden', 'miniaturized')
        for index, phase in enumerate(PHASES):
            inside = [event for event in states if type(event.get('uptime_seconds')) in (int, float)
                      and math.isfinite(event['uptime_seconds'])
                      and boundaries[index]+2 <= event['uptime_seconds']+lo
                      and event['uptime_seconds']+hi <= boundaries[index+1]-2]
            inside.sort(key=lambda event: event['uptime_seconds'])
            times = sorted({event['uptime_seconds'] for event in inside})
            span = times[-1]-times[0] if times else 0
            gap = max((b-a for a, b in zip(times, times[1:])), default=0)
            foreground = phase != 'studio_front'
            def matches(event):
                if not foreground:
                    return event.get('app_active') is False
                return all(event.get(k) is True for k in fields[:5]) and all(event.get(k) is False for k in fields[5:])
            mismatches = sum(not matches(event) for event in inside)
            enough = len(times) >= 3 and span >= 5 and gap <= 2.5
            result['phases'][phase] = {'status': 'VERIFIED' if enough and not mismatches else 'NOT_OBSERVED',
                'expected_fixture_active': foreground, 'observations': len(inside), 'distinct_timestamps': len(times),
                'span_s': span, 'largest_metadata_gap_s': gap, 'mismatched_observations': mismatches,
                'reason': None if enough and not mismatches else 'focus_metadata_mismatch' if mismatches else 'insufficient_contemporaneous_metadata',
                'field_counts': {field: {str(value): sum(event.get(field) is value for event in inside)
                                        for value in (True, False, None)} for field in fields}}
        if all(phase['status'] == 'VERIFIED' for phase in result['phases'].values()):
            result['status'] = 'VERIFIED'
    except (ValueError, KeyError, TypeError) as error:
        result['reason'] = str(error)
    return result


def owned_stop_command(slot, attempt):
    require(slot['attempt_id'] == attempt, 'Foreign output attempt; cleanup withheld')
    if not slot['native_busy']:
        return None
    return 'stop_output_target' if slot['phase'] == 'active' else 'cancel_output_target'


def unique_owned_tone(inputs, name, prior_ids):
    """Identify a newly admitted exact tone, independent of input list order."""
    require(isinstance(inputs, list) and len(inputs) <= 8 and all(isinstance(item, dict) for item in inputs),
            'Bounded mixer input objects required')
    candidates = [item for item in inputs if isinstance(item, dict)
                  and isinstance(item.get('id'), str) and bool(item['id']) and item['id'] not in prior_ids
                  and item.get('name') == name and item.get('source') == {'kind': 'tone'}
                  and item.get('muted') is False]
    require(len(candidates) == 1, 'Exactly one new owned unmuted tone is required')
    require(sum(item.get('id') == candidates[0]['id'] for item in inputs) == 1, 'Tone ID must be unique')
    return candidates[0]['id']

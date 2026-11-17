#!/usr/bin/env python3
"""First H11 real-media increment: text, managed PNG alpha, rectangle and circle.

Requires the signed, idle app and the parent's exclusive physical-test lock.
Uses owned fixtures only; no device capture or public output. It never opens the
app, acquires a lock or changes signing. --with-video additionally exercises a
small owned H.264/AAC clip, pause/restart/loop and explicitly disabled media audio.
Reports, decoded review frames, input fixtures and recordings remain under var/.
"""
import argparse
import hashlib
import json
import math
import pathlib
import shutil
import statistics
import struct
import subprocess
import time
import zlib

from h7_support import Client, ROOT, EVIDENCE, EXE, process_sample
from verify_h10_audio import tonal_amplitude

WIDTH, HEIGHT = 960, 540
BACKGROUND = (16, 32, 64)
GREEN = (32, 224, 96)
RECTANGLE = (40, 170, 230)
CIRCLE = (230, 60, 75)


def png(path, width, height, pixels, channels=4):
    """Encode an original, exact-pixel fixture or decoded frame using stdlib."""
    assert len(pixels) == width * height * channels
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\0' + pixels[y*width*channels:(y+1)*width*channels] for y in range(height))
    header = struct.pack('>IIBBBBB', width, height, 8, 6 if channels == 4 else 2, 0, 0, 0)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def fixture_png(path):
    # Hidden red cannot leak through the first band. The middle band is 50%
    # green; the last band is opaque green. Interior probes avoid chroma edges.
    pixels = bytes(channel for _y in range(96) for x in range(96)
                   for channel in ((255, 0, 0, 0) if x < 32 else (*GREEN, 128 if x < 64 else 255)))
    png(path, 96, 96, pixels)


def cli(op, **fields):
    p = subprocess.run([str(EXE), 'ctl', json.dumps({'op': op, **fields})],
                       capture_output=True, text=True, timeout=12)
    value = json.loads(p.stdout)
    assert value['ok'], value
    return value


def sources(state):
    return {s['id']: s for s in state['overlays']['runtime']['sources']}


def import_asset(c, path, expected=True):
    # AssetCatalog created this private inbox when the app started. A verifier
    # must not create a permissive directory or send an arbitrary host path.
    inbox = ROOT / 'var/imports'
    assert inbox.is_dir() and not inbox.is_symlink() and inbox.stat().st_mode & 0o077 == 0
    shutil.copyfile(path, inbox / path.name)
    response = c.call('import_asset', file_name=path.name)
    operation = response['result']['import']['operation_id']
    completed = c.wait(lambda s: s['overlays']['import'].get('operation_id') == operation
                       and s['overlays']['import']['phase'] in ('completed', 'failed'), timeout=80)
    result = completed['overlays']['import']
    assert (result['phase'] == 'completed') == expected, result
    return result


def text_definition(content, color=0xffffff):
    return {'kind': 'text', 'text': content, 'font': 'Helvetica', 'size': 40,
            'color': color, 'opacity': 1.0, 'align': 'left', 'width': 600, 'height': 130,
            'background': None, 'background_opacity': 0.0, 'outline': False}


def shape_definition(shape, width, height, color, border=None, border_width=0):
    return {'kind': 'shape', 'shape': shape, 'width': width, 'height': height,
            'color': color, 'opacity': 1.0, 'border_color': border, 'border_width': border_width}


def frame(path, second):
    raw = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
                                   '-ss', str(second), '-frames:v', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    assert len(raw) == WIDTH * HEIGHT * 3
    return raw


def region(raw, box):
    x, y, width, height = box
    return [tuple(raw[(row * WIDTH + col)*3:(row * WIDTH + col)*3+3])
            for row in range(y, y+height) for col in range(x, x+width)]


def mean_color(raw, box):
    pixels = region(raw, box)
    return [statistics.mean(p[c] for p in pixels) for c in range(3)]


def near(actual, expected, tolerance=20):
    return max(abs(a-b) for a, b in zip(actual, expected)) <= tolerance


def srgb_blend(foreground, background, alpha):
    def linear(value):
        x = value / 255
        return x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4
    def srgb(value):
        return 255 * (12.92 * value if value <= .0031308 else 1.055 * value ** (1 / 2.4) - .055)
    return [srgb(alpha*linear(f) + (1-alpha)*linear(b)) for f, b in zip(foreground, background)]


def fixture_frame_identity(recording, source_clip, pause_stage, moving_stage, out):
    """Identify held source content across GOPs, not H.264 reconstruction noise.

    The owned two-second fixture has 60 distinct frames. A stopped image can
    reconstruct differently at a new I-frame: the saved failed run changed 983
    pixels by >15 at its I-frame although both images matched original frame 55.
    Match four samples against every original frame with explicit confidence,
    and require real playing samples to resolve to different fixture frames.
    This is a fixture-specific identity gate, not a general motion detector.
    """
    box = (720, 410, 192, 108)
    x, y, width, height = box
    frame_bytes = width * height * 3
    raw = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(source_clip),
                                   '-vf', 'scale=192:108:flags=bicubic', '-pix_fmt', 'rgb24',
                                   '-f', 'rawvideo', '-'])
    assert len(raw) == 60 * frame_bytes, ('unexpected controlled fixture frames', len(raw))
    originals = [raw[i*frame_bytes:(i+1)*frame_bytes] for i in range(60)]
    assert len(set(originals)) == 60, 'controlled fixture needs unique source frames'

    def identify(second, label):
        decoded = frame(recording, second)
        crop = b''.join(decoded[(row*WIDTH+x)*3:(row*WIDTH+x+width)*3]
                        for row in range(y, y+height))
        scores = sorted((sum(abs(a-b) for a, b in zip(crop, original))/frame_bytes, i)
                        for i, original in enumerate(originals))
        error, index = scores[0]
        runner = scores[1][0]
        # Absolute fit rejects blank/unrelated images; separation rejects an
        # ambiguous nearest match. Both previous real runs separate by >=1.7.
        assert error <= 20 and runner-error >= .5 and runner >= error*1.03, (
            'ambiguous controlled source-frame identity', second, scores[:3])
        png(out / (label + '.png'), width, height, crop, channels=3)
        return {'sample_seconds': second, 'source_frame': index, 'source_pts': index/30,
                'mean_absolute_rgb_error': error, 'runner_up_error': runner,
                'identity_margin': runner-error}

    paused = [identify(pause_stage['start']+offset, 'pause-identity-' + str(i))
              for i, offset in enumerate((.6, 1, 1.6, 2.4))]
    assert len({v['source_frame'] for v in paused}) == 1, ('paused source content advanced', paused)
    playing = [identify(moving_stage['start']+offset, 'restart-identity-' + str(i))
               for i, offset in enumerate((1, 1.6))]
    assert playing[0]['source_frame'] != playing[1]['source_frame'], ('playing source identity stayed fixed', playing)
    native = []
    for sample in pause_stage['samples']:
        videos = [v for v in sources(sample['state']).values() if v['kind'] == 'video']
        assert len(videos) == 1 and videos[0]['media_state'] == 'paused', videos
        native.append(videos[0]['media_time_ms'])
    assert native and len(set(native)) == 1, ('paused native time advanced', native)
    source_index = paused[0]['source_frame']
    png(out / 'paused-original-source.png', width, height, originals[source_index], channels=3)
    return {'fixture_sha256': hashlib.sha256(pathlib.Path(source_clip).read_bytes()).hexdigest(),
            'paused': paused, 'playing_control': playing, 'native_paused_media_time_ms': native[0],
            'gate': 'same unambiguous original frame at four pause times; distinct frames while playing'}


def verify_pixels(path, stages, out, source_clip=None):
    selected = {s['name']: s for s in stages}
    frames = {name: frame(path, selected[name]['start'] + 1.3) for name in ('baseline', 'updated', 'empty', 'center', 'right')}
    for name, raw in frames.items():
        png(out / (name + '.png'), WIDTH, HEIGHT, raw, channels=3)
    baseline = frames['baseline']
    measurements = {
        'background_rgb': mean_color(baseline, (860, 30, 40, 40)),
        'transparent_rgb': mean_color(baseline, (54, 250, 30, 40)),
        'half_alpha_rgb': mean_color(baseline, (118, 250, 30, 40)),
        'opaque_rgb': mean_color(baseline, (182, 250, 30, 40)),
        'rectangle_rgb': mean_color(baseline, (420, 280, 40, 30)),
        'circle_center_rgb': mean_color(baseline, (680, 290, 24, 24)),
        'circle_corner_rgb': mean_color(baseline, (623, 233, 10, 10)),
        'circle_border_rgb': mean_color(baseline, (622, 299, 4, 12)),
    }
    assert near(measurements['background_rgb'], BACKGROUND), measurements
    assert near(measurements['transparent_rgb'], BACKGROUND), measurements
    assert near(measurements['opaque_rgb'], GREEN), measurements
    # motive_visual explicitly composes SDR in encoded sRGB with framebuffer
    # sRGB disabled. The linear-light model is diagnostic, never an alternative
    # pass condition. This catches double alpha multiplication in that pipeline.
    alpha = 128 / 255
    models = {'encoded_rgb': [alpha*f+(1-alpha)*b for f, b in zip(GREEN, BACKGROUND)],
              'linear_light': srgb_blend(GREEN, BACKGROUND, alpha)}
    errors = {name: max(abs(a-b) for a, b in zip(measurements['half_alpha_rgb'], expected))
              for name, expected in models.items()}
    assert errors['encoded_rgb'] <= 12, (measurements, models, errors)
    assert BACKGROUND[1] + 55 < measurements['half_alpha_rgb'][1] < GREEN[1] - 35
    assert near(measurements['rectangle_rgb'], RECTANGLE), measurements
    assert near(measurements['circle_center_rgb'], CIRCLE), measurements
    assert near(measurements['circle_corner_rgb'], BACKGROUND), measurements
    assert near(measurements['circle_border_rgb'], (255, 223, 64)), measurements
    text_box = (40, 40, 600, 130)
    before = region(frames['baseline'], text_box)
    after = region(frames['updated'], text_box)
    empty = region(frames['empty'], text_box)
    white = sum(min(p) > 190 and max(p)-min(p) < 45 for p in before)
    yellow = sum(p[0] > 190 and p[1] > 150 and p[2] < 130 for p in after)
    changed = sum(max(abs(a-b) for a, b in zip(x, y)) > 40 for x, y in zip(before, after))
    remaining = sum(not near(p, BACKGROUND) for p in empty)
    assert white > 200 and yellow > 200 and changed > 500, (white, yellow, changed)
    assert remaining < len(empty) * .005, ('empty text retained pixels', remaining)
    measurements.update({'alpha_models': models, 'alpha_model_errors': errors,
                         'white_text_pixels_before': white, 'yellow_text_pixels_after': yellow,
                         'changed_text_pixels': changed, 'empty_text_nonbackground_pixels': remaining,
                         'review_frames': {name: str(out / (name + '.png')) for name in frames}})
    aligned = {}
    for name in ('center', 'right'):
        pixels = region(frames[name], text_box)
        xs = [i % 600 for i, p in enumerate(pixels) if min(p) > 190 and max(p)-min(p) < 45]
        assert len(xs) > 200, (name, len(xs))
        aligned[name] = {'left': min(xs), 'right': max(xs)}
    assert abs((aligned['center']['left']+aligned['center']['right'])/2-300) < 15, aligned
    assert 580 < aligned['right']['right'] < 600 and aligned['right']['left'] > aligned['center']['left']+100, aligned
    measurements['text_block_alignment'] = aligned
    if 'paused_video' in selected:
        box = (720, 410, 192, 108)
        paused = selected['paused_video']['start']
        moving = selected['restarted_video']['start']
        def changes(start):
            a = region(frame(path, start+1), box)
            b = region(frame(path, start+1.6), box)
            return sum(max(abs(x-y) for x, y in zip(p, q)) > 15 for p, q in zip(a, b))
        still_changes, live_changes = changes(paused), changes(moving)
        loop_changes = changes(selected['empty']['start'])
        assert source_clip is not None, 'controlled source clip required for pause identity'
        identity = fixture_frame_identity(path, source_clip, selected['paused_video'],
                                          selected['restarted_video'], out)
        assert live_changes > 300, ('restarted clip did not move', live_changes)
        assert loop_changes > 300, ('2-second clip stopped looping after 6 seconds', loop_changes)
        measurements['video_pause_restart'] = {'paused_changed_pixels': still_changes, 'playing_changed_pixels': live_changes,
                                              'loop_changed_pixels_after_6_seconds': loop_changes,
                                              'source_frame_identity': identity,
                                              'paused_pixel_difference_note': 'Diagnostic raw H.264 difference, including keyframe requantization; acceptance uses original fixture identity.'}
    return measurements


def verify_media(path, stages, with_video):
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(path)]))
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    assert (video['codec_name'], video['width'], video['height'], video['avg_frame_rate']) == ('h264', WIDTH, HEIGHT, '30/1'), video
    assert (audio['codec_name'], audio['sample_rate'], audio['channels']) == ('aac', '48000', 2), audio
    assert int(video['nb_read_frames']) >= (stages[-1]['end']-.2) * 28.5
    decode = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-f', 'null', '-'], capture_output=True, check=True)
    assert not decode.stderr, decode.stderr
    data = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vn', '-af', 'pan=mono|c0=c0', '-ar', '48000', '-f', 'f32le', '-'])
    samples = struct.unpack('<%df' % (len(data)//4), data)
    middle = samples[48000:96000]
    rms = math.sqrt(sum(x*x for x in middle)/len(middle))
    peak = max(abs(x) for x in samples)
    assert rms > .01 and peak < .5, (rms, peak)
    tone = tonal_amplitude(middle, 440)
    media_audio = tonal_amplitude(middle, 997)
    assert tone > .01, tone
    if with_video:
        assert media_audio < tone*.01 + 1e-6, ('media audio leaked into H10', tone, media_audio)
    packets = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_packets', '-show_entries', 'packet=codec_type,pts_time,dts_time', '-of', 'json', str(path)]))['packets']
    frame_pts = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)]))['frames']
    timestamps = {}
    for kind in ('audio', 'video'):
        typed = [p for p in packets if p['codec_type'] == kind]
        dts = [float(p['dts_time']) for p in typed if 'dts_time' in p]
        assert all(b > a for a, b in zip(dts, dts[1:]))
        pts = [float(p['pts_time']) for p in typed] if kind == 'audio' else [float(f['best_effort_timestamp_time']) for f in frame_pts]
        gaps = [b-a for a, b in zip(pts, pts[1:])]
        assert min(gaps) > 0
        if kind == 'audio':
            assert max(gaps) <= .023, ('audio PTS gap', max(gaps))
        else:
            assert max(gaps[:-4]) <= .035, ('video interior PTS gap', max(gaps[:-4]))
        timestamps[kind] = {'samples': len(pts), 'packets_without_dts': len(typed)-len(dts),
                            'max_gap_ms': max(gaps)*1000, 'max_interior_gap_ms': max(gaps[:-4])*1000}
    return {'probe': probe, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'left_channel_rms': rms, 'decoded_peak': peak, 'a440': tone, 'a997': media_audio,
            'timestamps': timestamps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-video', action='store_true')
    args = parser.parse_args()
    run = EVIDENCE / ('h11-visuals-' + str(time.time_ns()))
    run.mkdir(parents=True)
    report = {'ok': False, 'with_video': args.with_video, 'run': str(run), 'stages': []}
    c = None
    scene_id = None
    created_sources, created_assets, audio_id = [], [], None
    initial = None
    configuration_changed = False
    recording_owned = False
    try:
        c = Client()
        initial = c.state()
        report['initial'] = initial
        assert initial['output'] == 'idle' and not initial['audio_mixer']['store']['inputs']
        assert all(s['spec']['kind'] in ('pattern', 'overlay') for s in initial['project']['graph']['sources'])
        caps = c.call('overlay_capabilities')['result']
        report['capabilities'] = caps
        for name in ('text_ft2_source', 'image_source') + (('ffmpeg_source',) if args.with_video else ()):
            assert caps['native']['sources'][name]['available'], (name, caps)
        assert caps['media_audio'] == 'disabled_mixers_0_monitoring_off'
        existing_assets = {a['id'] for a in c.call('list_assets')['result']['assets']}
        denied = c.call('import_asset', expect=False, file_name='../../outside.png')
        assert denied['error']['code'] == 'INVALID_IMPORT_NAME', denied
        invalid = run / ('broken-' + run.name + '.png')
        invalid.write_bytes(b'\x89PNG\r\n\x1a\ninvalid')
        failed = import_asset(c, invalid, expected=False)
        assert failed['error']['code'] == 'ASSET_IMAGE_INVALID', failed
        report['invalid_import'] = failed
        original = run / ('alpha-' + run.name + '.png')
        fixture_png(original)
        asset = import_asset(c, original)['asset']
        report['image_asset'] = asset
        if asset['id'] not in existing_assets:
            created_assets.append(asset['id'])
        video_asset = None
        if args.with_video:
            clip = run / ('video-' + run.name + '.mp4')
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30',
                            '-f', 'lavfi', '-i', 'sine=frequency=997:sample_rate=48000', '-t', '2', '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(clip)], check=True)
            video_asset = import_asset(c, clip)['asset']
            assert video_asset['has_audio']
            report['video_asset'] = video_asset
            if video_asset['id'] not in existing_assets:
                created_assets.append(video_asset['id'])
        c.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0})
        configuration_changed = True
        c.call('set_variant', variant='horizontal')
        s = c.call('create_scene', name='H11 visual verification')['state']
        scene_id = s['project']['graph']['active_scene']
        def add(name, definition, rect, order):
            r = c.call('create_overlay', scene_id=scene_id, name=name, definition=definition)
            source_id = r['result']['source_id']
            created_sources.append(source_id)
            scene = next(s for s in r['state']['project']['graph']['scenes'] if s['id'] == scene_id)
            layer = next(l for l in scene['layers'] if l['source_id'] == source_id)
            x, y, width, height = rect
            c.call('set_transform', scene_id=scene_id, layer_id=layer['id'], variant='horizontal',
                   transform={'x': x, 'y': y, 'width': width, 'height': height, 'visible': True, 'order': order})
            return source_id
        add('Controlled background', shape_definition('rectangle', 960, 540, 0x102040), (0, 0, 960, 540), 0)
        text_id = add('UTF-8 text', text_definition('H11 Áé ñ ✓\nNative text'), (40, 40, 600, 130), 4)
        add('Managed PNG alpha', {'kind': 'image', 'asset_id': asset['id'], 'opacity': 1.0}, (40, 220, 192, 192), 1)
        add('Rectangle', shape_definition('rectangle', 150, 95, 0x28aae6, 0xf0f0f0, 8), (370, 250, 150, 95), 2)
        add('Circle', shape_definition('circle', 150, 150, 0xe63c4b, 0xffdf40, 8), (620, 230, 150, 150), 3)
        video_id = None
        if video_asset:
            video_id = add('Silent local media', {'kind': 'video', 'asset_id': video_asset['id'], 'opacity': 1.0, 'looping': True}, (720, 410, 192, 108), 5)
        denied = c.call('remove_asset', expect=False, asset_id=asset['id'])
        assert denied['error']['code'] == 'ASSET_IN_USE', denied
        s = c.call('add_audio_input', name='H11 controlled tone', source={'kind': 'tone'})['state']
        audio_id = next(i['id'] for i in s['audio_mixer']['store']['inputs'] if i['source']['kind'] == 'tone')
        c.call('set_audio_gain', input_id=audio_id, gain_db=-6)
        c.call('set_audio_mute', input_id=audio_id, muted=False)
        ready = c.wait(lambda s: not s['issues'] and not s['recovery_required']
                       and all(source_id in sources(s) and not sources(s)[source_id]['health'] for source_id in created_sources)
                       and any(i['id'] == audio_id and i['phase'] == 'ready' for i in s['audio_mixer']['runtime']['inputs']))
        assert ready['project']['version'] == 4
        shared = cli('overlay_state')
        assert shared['pid'] == ready['pid'] and shared['result']['definitions'] == ready['overlays']['definitions']
        if video_id:
            assert sources(ready)[video_id]['audio_mixers'] == 0
            c.call('overlay_event', source_id=video_id, event='restart')
        started = c.call('start_recording')['state']
        recording_owned = True
        started = c.wait(lambda s: s['output'] == 'recording')
        start = time.monotonic()
        path = pathlib.Path(started['output_path'])
        report.update({'started': started, 'path': str(path)})
        native = sources(started)
        last_cpu, _ = process_sample(started['pid'])
        last_time, last_frames = start, started['stats']['encoded_frames']
        def hold(name):
            nonlocal last_cpu, last_time, last_frames
            stage = {'name': name, 'start': time.monotonic()-start, 'samples': []}
            report['stages'].append(stage)
            until = time.monotonic() + 3
            while time.monotonic() < until:
                time.sleep(.2)
                state = c.state()
                now = time.monotonic()
                cpu, rss = process_sample(state['pid'])
                assert state['pid'] == started['pid'] and state['output'] == 'recording' and state['output_path'] == started['output_path']
                assert not state['issues'] and not state['recovery_required'], state['issues']
                assert state['stats']['encoded_frames'] >= last_frames
                assert state['transition']['source_instances_created'] == started['transition']['source_instances_created']
                assert state['transition']['scenes_built'] == started['transition']['scenes_built']
                assert state['audio_mixer']['store'] == started['audio_mixer']['store']
                assert state['audio_mixer']['runtime']['mix']['clipped_blocks'] == started['audio_mixer']['runtime']['mix']['clipped_blocks']
                current = sources(state)
                for source_id in created_sources:
                    assert current[source_id]['instance_id'] == native[source_id]['instance_id']
                    assert current[source_id]['child_instances_created'] == native[source_id]['child_instances_created']
                    assert not current[source_id]['health'], current[source_id]
                stage['samples'].append({'seconds': now-start, 'cpu_percent': 100*(cpu-last_cpu)/(now-last_time), 'rss_mib': rss, 'state': state})
                last_cpu, last_time, last_frames = cpu, now, state['stats']['encoded_frames']
            stage['end'] = time.monotonic()-start
        hold('baseline')
        c.call('update_overlay', source_id=text_id, definition=text_definition('MCP CAMBIO\nñ Áé ✓', 0xffe040))
        hold('updated')
        c.call('update_overlay', source_id=text_id, definition=text_definition(''))
        hold('empty')
        for alignment in ('center', 'right'):
            definition = text_definition('ALIGN')
            definition['align'] = alignment
            c.call('update_overlay', source_id=text_id, definition=definition)
            hold(alignment)
        if video_id:
            c.call('overlay_event', source_id=video_id, event='pause')
            c.wait(lambda s: sources(s)[video_id]['media_state'] == 'paused')
            hold('paused_video')
            c.call('overlay_event', source_id=video_id, event='restart')
            c.wait(lambda s: sources(s)[video_id]['media_state'] == 'playing')
            hold('restarted_video')
            c.call('overlay_event', source_id=video_id, event='stop')
            c.wait(lambda s: sources(s)[video_id]['media_state'] == 'stopped')
            hold('stopped_video')
            c.call('overlay_event', source_id=video_id, event='play')
            c.wait(lambda s: sources(s)[video_id]['media_state'] == 'playing')
            hold('playing_video')
        stopped = c.stop()
        assert stopped['end']['output'] == 'idle' and stopped['end']['output_code'] == 0
        recording_owned = False
        report['stopped'] = stopped
        report['media'] = verify_media(path, report['stages'], args.with_video)
        report['pixels'] = verify_pixels(path, report['stages'], run, clip if args.with_video else None)
        samples = [sample for stage in report['stages'] for sample in stage['samples']]
        report['performance'] = {'cpu_median': statistics.median(s['cpu_percent'] for s in samples),
                                 'rss_median_mib': statistics.median(s['rss_mib'] for s in samples),
                                 'rss_max_mib': max(s['rss_mib'] for s in samples),
                                 'stats_at_start': started['stats'], 'stats_at_end': stopped['end']['stats'],
                                 'note': 'Debug app process only; polling observer included. No performance improvement claim.'}
        report['ok'] = True
    except BaseException as failure:
        report['error'] = repr(failure)
        raise
    finally:
        errors = []
        def cleanup(action):
            try:
                action()
            except Exception as failure:
                errors.append(repr(failure))
        if c:
            cleanup(lambda: c.wait(lambda s: s['overlays']['import'] is None or s['overlays']['import']['phase'] != 'running', timeout=80))
            if recording_owned:
                cleanup(c.stop)
            if scene_id:
                cleanup(lambda: c.call('configure_transition', transition={'kind': 'cut', 'duration_ms': 0}))
                if initial:
                    cleanup(lambda: c.call('select_scene', scene_id=initial['project']['graph']['active_scene']))
                cleanup(lambda: c.call('remove_scene', scene_id=scene_id))
            for source_id in reversed(created_sources):
                cleanup(lambda: c.call('remove_source', source_id=source_id))
            for asset_id in created_assets:
                cleanup(lambda: c.call('remove_asset', asset_id=asset_id))
            if audio_id:
                cleanup(lambda: c.call('remove_audio_input', input_id=audio_id))
            if initial and configuration_changed:
                cleanup(lambda: c.call('set_variant', variant=initial['project']['variant']))
                cleanup(lambda: c.call('configure_transition', transition=initial['transition_configuration']))
            report['operations'] = c.ops
            cleanup(c.close)
        try:
            report['app_sha256'] = hashlib.sha256((ROOT/'target/Motive.app/Contents/MacOS/motive').read_bytes()).hexdigest()
        except OSError as failure:
            report['app_sha256_error'] = repr(failure)
        if errors:
            report['cleanup_errors'] = errors
            report['ok'] = False
        contents = json.dumps(report, indent=2)
        (run/'report.json').write_text(contents)
        (EVIDENCE/'h11-visuals.json').write_text(contents)
    assert report['ok'], report.get('cleanup_errors')
    print(json.dumps({'ok': True, 'report': str(run/'report.json'), 'recording': report['path'],
                      'media': report['media'], 'pixels': report['pixels'], 'performance': report['performance']}, indent=2))


if __name__ == '__main__':
    main()

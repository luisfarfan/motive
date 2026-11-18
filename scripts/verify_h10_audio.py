#!/usr/bin/env python3
"""Real audio pilot: physical mic hearing an owned 997 Hz speaker fixture + 440 Hz.
Requires exclusive device/bundle use, normal microphone permission, FFmpeg.
No simulated capture; speaker playback is explicitly part of this local test.
"""
import argparse
import hashlib
import json
import math
import pathlib
import struct
import subprocess
import time
import wave

ROOT = pathlib.Path(__file__).resolve().parents[1]
from verification_paths import verification_paths
VERIFY = verification_paths(ROOT)
EXE = VERIFY.client_executable
OUT = ROOT / 'var/evidence'


def ctl(op, expect=True, **fields):
    result = subprocess.run([str(EXE), 'ctl', json.dumps({'op': op, **fields})],
                            capture_output=True, text=True, timeout=12)
    value = json.loads(result.stdout)
    assert value['ok'] == expect, value
    return value


def wait(predicate, timeout=12):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        state = ctl('status')['state']
        if predicate(state):
            return state
        time.sleep(.2)
    raise AssertionError({'timeout': state})


def power(samples, freq):
    # Orthogonal projections on a whole-second segment; no FFT dependency.
    re = sum(x * math.cos(2 * math.pi * freq * i / 48000) for i, x in enumerate(samples))
    im = sum(x * math.sin(2 * math.pi * freq * i / 48000) for i, x in enumerate(samples))
    return 2 * math.hypot(re, im) / len(samples)


def tonal_amplitudes(samples, freq):
    # RMS of 100 ms Hann-windowed frequency amplitudes, never a coherent
    # average of phases over a second. Retains all windows, including dips.
    # This avoids cancelling a tone when phase changes within the measurement window.
    size = 4800
    weights = [.5-.5*math.cos(2*math.pi*i/(size-1)) for i in range(size)]
    cosine = [w*math.cos(2*math.pi*freq*i/48000) for i,w in enumerate(weights)]
    sine = [w*math.sin(2*math.pi*freq*i/48000) for i,w in enumerate(weights)]
    amplitudes = []
    for offset in range(0, len(samples)-size+1, size):
        chunk = samples[offset:offset+size]
        re = sum(x*w for x,w in zip(chunk,cosine))
        im = sum(x*w for x,w in zip(chunk,sine))
        amplitudes.append(2*math.hypot(re,im)/sum(weights))
    return amplitudes


def tonal_amplitude(samples, freq):
    amplitudes = tonal_amplitudes(samples, freq)
    return math.sqrt(sum(x*x for x in amplitudes)/len(amplitudes))


def isolated_tone_continuity(samples, stage, gain_db, downmix_factor=1.0):
    """Every 20 ms RMS window, stepped 10 ms, inside a mic-muted reference.

    The fixed +/-1 dB bound is against the generated tone's known level, not a
    fitted/selected good window. Retain every result before callers assert so a
    1024-sample interruption cannot hide in a one-second or median aggregate.
    downmix_factor only describes the pilot's existing stereo-to-mono decode;
    the mixer verifier measures channel 0 directly and uses 1.0.
    """
    size, step = 960, 480
    lo, hi = round((stage['start']+.2)*48000), round((stage['end']-.2)*48000)
    assert 0 <= lo < hi <= len(samples), (stage, len(samples))
    expected = 20*math.log10(.0630957344 * 10**(gain_db/20) * downmix_factor / math.sqrt(2))
    windows = []
    for offset in range(lo, hi-size+1, step):
        chunk = samples[offset:offset+size]
        level = 20*math.log10(max(math.sqrt(sum(x*x for x in chunk)/size), 1e-15))
        windows.append({'start_seconds': offset/48000, 'rms_dbfs': level,
                        'error_db': level-expected})
    assert len(windows) >= 50, len(windows)
    return {'ok': all(abs(w['error_db']) < 1 for w in windows),
            'expected_rms_dbfs': expected, 'gain_db': gain_db,
            'downmix_factor': downmix_factor, 'window_ms': 20, 'step_ms': 10,
            'action_margin_seconds': .2, 'tolerance_db': 1, 'windows': windows}


def decode(path):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', path, '-f', 'null', '-'],
                   check=True, capture_output=True)
    pcm = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', path,
                                  '-vn', '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'])
    return struct.unpack('<%df' % (len(pcm) // 4), pcm)


def stimulus(path, seconds=30):
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        second = b''.join(struct.pack('<h', int(7000 * math.sin(2 * math.pi * 997 * i / 48000))) for i in range(48000))
        wav.writeframes(second * seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--microphone-id', required=True)
    args = parser.parse_args()
    report = {'ok': False, 'stages': [], 'physical_hot_unplug': 'not tested'}
    playback = None
    try:
        state = ctl('status')['state']
        assert state['output'] == 'idle' and not state['audio_mixer']['store']['inputs']
        ctl('add_audio_input', name='Micrófono físico', source={'kind': 'microphone', 'device_id': args.microphone_id})
        state = ctl('add_audio_input', name='Tono controlado', source={'kind': 'tone'})['state']
        initial_instances = state['audio_mixer']['runtime']['instances_created'] - 2
        project = state['project']
        profiles = ctl('output_profiles')['store']
        inputs = state['audio_mixer']['store']['inputs']
        mic, tone = inputs[0]['id'], inputs[1]['id']
        reused = ctl('add_audio_input', name='Reutilizar micrófono', source=inputs[0]['source'])['state']
        assert reused['audio_mixer']['store'] == state['audio_mixer']['store']
        assert reused['audio_mixer']['runtime']['instances_created'] == initial_instances + 2
        assert ctl('set_audio_gain', expect=False, input_id=tone, gain_db=25)['error']['code'] == 'INVALID_AUDIO_GAIN'
        ctl('set_audio_gain', input_id=mic, gain_db=6)
        wait(lambda s: all(i['phase'] == 'ready' for i in s['audio_mixer']['runtime']['inputs']))
        fixture = ROOT / 'var/h10-speaker-997.wav'
        stimulus(fixture, 60)
        playback = subprocess.Popen(['afplay', '-v', '0.5', str(fixture)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        # References are inside the same real recording. A physical microphone
        # can contain 440 Hz-band energy, so a mixed projection cannot identify
        # digital gain or isolate the effect of muting that microphone.
        ctl('set_audio_mute', input_id=mic, muted=True)
        initial = ctl('start_recording')['state']
        started = time.monotonic()
        path = initial['output_path']
        report['path'] = path
        for label, operations in [
            ('tone_reference_high', []),
            ('tone_reference_low', [('set_audio_gain', {'input_id': tone, 'gain_db': -18})]),
            ('both', [('set_audio_gain', {'input_id': tone, 'gain_db': -6}),
                      ('set_audio_mute', {'input_id': mic, 'muted': False})]),
            ('tone_lower', [('set_audio_gain', {'input_id': tone, 'gain_db': -18})]),
            ('mic_muted', [('set_audio_mute', {'input_id': mic, 'muted': True})]),
            ('mic_unmuted', [('set_audio_mute', {'input_id': mic, 'muted': False})]),
            ('mic_disconnected', [('disconnect_audio_input', {'input_id': mic})]),
            ('mic_reconnected', [('reconnect_audio_input', {'input_id': mic})]),
        ]:
            for operation in operations:
                ctl(operation[0], **operation[1])
            stage = {'label': label, 'start': time.monotonic() - started, 'samples': []}
            for _ in range(12):
                time.sleep(.25)
                current = ctl('status')['state']
                assert current['output'] == 'recording' and current['pid'] == initial['pid']
                assert current['audio_mixer']['runtime']['instances_created'] == initial_instances + (3 if label == 'mic_reconnected' else 2)
                stage['samples'].append(current)
            stage['end'] = time.monotonic() - started
            report['stages'].append(stage)
        ctl('stop_output')
        final = wait(lambda s: s['output'] == 'idle')
        assert final['output_code'] == 0
        samples = decode(path)
        for stage in report['stages']:
            offset = int((stage['start'] + 1) * 48000)
            chunk = samples[offset:offset + 48000]
            a440, a997 = tonal_amplitudes(chunk, 440), tonal_amplitudes(chunk, 997)
            stage['decoded'] = {'rms': math.sqrt(sum(x*x for x in chunk)/len(chunk)),
                                'peak': max(abs(x) for x in chunk),
                                'coherent_amplitude_440': power(chunk, 440),
                                'amplitude_440': math.sqrt(sum(x*x for x in a440)/len(a440)),
                                'amplitude_997': math.sqrt(sum(x*x for x in a997)/len(a997)),
                                'windows_100ms': [{'start_seconds': (offset+i*4800)/48000,
                                                  'amplitude_440': a, 'amplitude_997': b}
                                                 for i, (a, b) in enumerate(zip(a440, a997))]}
            stage['controls'] = stage['samples'][0]['audio_mixer']['store']['inputs']
            if stage['label'].startswith('tone_reference_'):
                for current in stage['samples']:
                    controls = current['audio_mixer']['store']['inputs']
                    assert next(i for i in controls if i['id']==mic)['muted']
                    expected_gain = -6 if stage['label']=='tone_reference_high' else -18
                    assert next(i for i in controls if i['id']==tone)['gain_db'] == expected_gain
        measured = {s['label']: s['decoded'] for s in report['stages']}
        both, lower, muted, unmuted, disconnected, reconnected = [measured[name] for name in
            ('both', 'tone_lower', 'mic_muted', 'mic_unmuted', 'mic_disconnected', 'mic_reconnected')]
        high_ref, low_ref = measured['tone_reference_high'], measured['tone_reference_low']
        report['gain_reference'] = 'same-recording mic-muted tone_reference_high/low; unchanged Hann estimator'
        report['mixed_gain_delta_db'] = 20*math.log10(lower['amplitude_440']/both['amplitude_440'])
        report['mixed_reference_independence_db'] = {
            name: 20*math.log10(measured[name]['amplitude_440']/lower['amplitude_440'])
            for name in ('mic_muted', 'mic_disconnected')}
        report['isolated_reference_continuity'] = {
            name: isolated_tone_continuity(samples, next(s for s in report['stages'] if s['label']==name), gain,
                                          downmix_factor=math.sqrt(2))
            for name, gain in [('tone_reference_high', -6), ('tone_reference_low', -18)]}
        assert all(v['ok'] for v in report['isolated_reference_continuity'].values()), report['isolated_reference_continuity']
        assert both['amplitude_440'] > .005 and both['amplitude_997'] > .00001, both
        report['gain_delta_db'] = 20*math.log10(low_ref['amplitude_440']/high_ref['amplitude_440'])
        assert -13 < report['gain_delta_db'] < -11, report['gain_delta_db']
        assert muted['amplitude_997'] < lower['amplitude_997']*.1, [lower, muted]
        assert unmuted['amplitude_997'] > muted['amplitude_997']*10, [muted, unmuted]
        assert abs(20*math.log10(muted['amplitude_440']/low_ref['amplitude_440'])) < .5
        report['peak'] = max(abs(x) for x in samples)
        assert report['peak'] < .98, report['peak']
        assert final['audio_mixer']['runtime']['mix']['clipped_blocks'] == 0
        assert disconnected['amplitude_997'] < lower['amplitude_997']*.1
        assert abs(20*math.log10(disconnected['amplitude_440']/low_ref['amplitude_440'])) < .5
        assert reconnected['amplitude_997'] > disconnected['amplitude_997']*10
        store = ctl('save_audio_mixer')['state']['audio_mixer']['store']
        for entry in store['inputs']: ctl('remove_audio_input', input_id=entry['id'])
        restored = ctl('load_audio_mixer')['state']
        wait(lambda s: all(i['phase'] == 'ready' for i in s['audio_mixer']['runtime']['inputs']))
        assert restored['audio_mixer']['store'] == store and restored['project'] == project
        assert ctl('output_profiles')['store'] == profiles
        assert ctl('audio_mixer')['audio_mixer']['store'] == store
        report['restored_store'] = store
        report['ok'] = True
    except BaseException as failure:
        report['error'] = repr(failure)
        raise
    finally:
        if playback:
            playback.terminate()
            playback.wait(timeout=5)
        try:
            ctl('stop_output')
            wait(lambda s: s['output'] == 'idle')
            for entry in ctl('audio_mixer')['audio_mixer']['store']['inputs']:
                ctl('remove_audio_input', input_id=entry['id'])
        except Exception as failure:
            report['cleanup_error'] = repr(failure)
        app = VERIFY.app_executable
        report['app_sha256'] = hashlib.sha256(app.read_bytes()).hexdigest()
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'h10-pilot.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'stages'}, indent=2))


if __name__ == '__main__':
    main()

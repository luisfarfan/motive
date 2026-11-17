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
EXE = ROOT / 'target/debug/motive'
OUT = ROOT / 'var/evidence'


def ctl(op, **fields):
    result = subprocess.run([str(EXE), 'ctl', json.dumps({'op': op, **fields})],
                            capture_output=True, text=True, timeout=12, check=True)
    value = json.loads(result.stdout)
    assert value['ok'], value
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
        inputs = state['audio_mixer']['store']['inputs']
        mic, tone = inputs[0]['id'], inputs[1]['id']
        reused = ctl('add_audio_input', name='Reutilizar micrófono', source=inputs[0]['source'])['state']
        assert reused['audio_mixer']['store'] == state['audio_mixer']['store']
        assert reused['audio_mixer']['runtime']['instances_created'] == 2
        ctl('set_audio_gain', input_id=mic, gain_db=6)
        wait(lambda s: all(i['phase'] == 'ready' for i in s['audio_mixer']['runtime']['inputs']))
        fixture = ROOT / 'var/h10-speaker-997.wav'
        stimulus(fixture)
        playback = subprocess.Popen(['afplay', '-v', '0.5', str(fixture)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        initial = ctl('start_recording')['state']
        started = time.monotonic()
        path = initial['output_path']
        report['path'] = path
        for label, operation in [
            ('both', None),
            ('tone_lower', ('set_audio_gain', {'input_id': tone, 'gain_db': -18})),
            ('mic_muted', ('set_audio_mute', {'input_id': mic, 'muted': True})),
            ('mic_unmuted', ('set_audio_mute', {'input_id': mic, 'muted': False})),
        ]:
            if operation:
                ctl(operation[0], **operation[1])
            stage = {'label': label, 'start': time.monotonic() - started, 'samples': []}
            for _ in range(12):
                time.sleep(.25)
                current = ctl('status')['state']
                assert current['output'] == 'recording' and current['pid'] == initial['pid']
                assert current['audio_mixer']['runtime']['instances_created'] == 2
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
            stage['decoded'] = {'rms': math.sqrt(sum(x*x for x in chunk)/len(chunk)),
                                'peak': max(abs(x) for x in chunk),
                                'amplitude_440': power(chunk, 440), 'amplitude_997': power(chunk, 997)}
        both, lower, muted, unmuted = [s['decoded'] for s in report['stages']]
        assert both['amplitude_440'] > .005 and both['amplitude_997'] > .00001, report['stages'][0]['decoded']
        report['gain_delta_db'] = 20*math.log10(lower['amplitude_440']/both['amplitude_440'])
        assert -13 < report['gain_delta_db'] < -11, report['gain_delta_db']
        assert muted['amplitude_997'] < lower['amplitude_997']*.1, [lower, muted]
        assert unmuted['amplitude_997'] > muted['amplitude_997']*10, [muted, unmuted]
        assert abs(20*math.log10(muted['amplitude_440']/lower['amplitude_440'])) < .5
        report['peak'] = max(abs(x) for x in samples)
        assert report['peak'] < .98, report['peak']
        assert final['audio_mixer']['runtime']['mix']['clipped_blocks'] == 0
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
        except Exception as failure:
            report['cleanup_error'] = repr(failure)
        app = ROOT / 'target/Motive.app/Contents/MacOS/motive'
        report['app_sha256'] = hashlib.sha256(app.read_bytes()).hexdigest()
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'h10-pilot.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'stages'}, indent=2))


if __name__ == '__main__':
    main()

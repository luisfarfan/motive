#!/usr/bin/env python3
"""Generate controlled WAV fixtures or benchmark an explicitly supplied local ASR.

No downloads, microphone, playback, permissions, socket, Motive API or Show
Control calls. The corpus is synthetic and cannot certify human/live detection.
"""
import argparse
import hashlib
import json
import math
import os
import pathlib
import platform
import random
import re
import signal
import statistics
import struct
import subprocess
import tempfile
import time
import unicodedata
import wave

RATE = 16000
ROOT = pathlib.Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def read_wav(path):
    with wave.open(str(path)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getcomptype()) != (RATE, 1, 2, 'NONE'):
            raise ValueError(f'Expected mono PCM s16 16 kHz WAV: {path}')
        if wav.getnframes() > RATE * 60:
            raise ValueError('Fixture exceeds 60 second bound')
        raw = wav.readframes(wav.getnframes())
    return [value[0] / 32768 for value in struct.iter_unpack('<h', raw)]


def write_wav(path, samples):
    if not samples or max(abs(x) for x in samples) >= 1:
        raise ValueError('Fixture has no samples or would clip')
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((1, 2, RATE, len(samples), 'NONE', 'not compressed'))
        wav.writeframes(b''.join(struct.pack('<h', round(x * 32767)) for x in samples))


def normalize(samples, peak=0.5):
    maximum = max(abs(x) for x in samples)
    return [x * peak / maximum for x in samples] if maximum else samples


def noise(seconds, seed=714):
    rng = random.Random(seed)
    return [rng.uniform(-0.12, 0.12) for _ in range(int(seconds * RATE))]


def music(seconds):
    # Original procedural arpeggio, no samples or copyrighted song.
    notes = (220, 277.18, 329.63, 440, 329.63, 277.18)
    result = []
    for n in range(int(seconds * RATE)):
        t = n / RATE
        phase = t % 0.4
        hz = notes[int(t / 0.4) % len(notes)]
        envelope = min(1, phase / 0.015) * math.exp(-phase * 5)
        result.append(0.13 * envelope * (math.sin(2 * math.pi * hz * t) + 0.3 * math.sin(4 * math.pi * hz * t)))
    return result


def game_noise(seconds):
    result = noise(seconds, 715)
    for n in range(len(result)):
        t = n / RATE
        pulse = (t % 0.65) < 0.09
        result[n] = result[n] * (1 if pulse else 0.15) + (0.16 * math.sin(2 * math.pi * (390 * t + 160 * t * t)) if pulse else 0)
    return result


def prepare(args):
    output = args.output.absolute()
    if output.exists():
        raise ValueError('Choose a new corpus directory; existing evidence is never replaced')
    voices = subprocess.check_output(['/usr/bin/say', '-v', '?'], text=True)
    if not any(re.match(re.escape(args.voice) + r'\s+es[_-]', line) for line in voices.splitlines()):
        raise ValueError('Voice must already appear in say -v ? as an installed Spanish voice')
    output.mkdir(parents=True)
    cases = []

    def add(name, samples, expected, category, source, challenge=False):
        path = output / (name + '.wav')
        write_wav(path, samples)
        actual = read_wav(path)
        rms = math.sqrt(sum(x*x for x in actual) / len(actual))
        cases.append({'id': name, 'file': path.name, 'sha256': digest(path),
                      'seconds': len(actual) / RATE, 'expected_keyword': expected,
                      'category': category, 'source': source, 'challenge': challenge,
                      'peak_dbfs': 20 * math.log10(max(abs(x) for x in actual)) if any(actual) else None,
                      'rms_dbfs': 20 * math.log10(rms) if rms else None,
                      'clipped_samples': sum(abs(x) >= 32767/32768 for x in actual)})

    def tts(name, text, expected, category, rate=165, challenge=False):
        with tempfile.TemporaryDirectory(prefix='motive-voice-') as directory:
            raw = pathlib.Path(directory) / 'say.wav'
            subprocess.run(['/usr/bin/say', '-v', args.voice, '-r', str(rate),
                            '-o', str(raw), '--file-format=WAVE', '--data-format=LEI16@16000', text],
                           check=True, timeout=30, capture_output=True)
            speech = normalize(read_wav(raw))
        samples = [0.0] * (RATE // 2) + speech + [0.0] * RATE
        add(name, samples, expected, category, {'type': 'local_tts', 'text': text, 'voice': args.voice, 'words_per_minute': rate}, challenge)
        return samples

    goal = tts('goal_normal', '¡Gol!', True, 'keyword')
    tts('goal_slow', '¡Gol!', True, 'keyword_slow_synthetic', rate=85)
    tts('goal_elongated_text', '¡Gooooooool!', True, 'elongated_spelling_not_human_shout')
    tts('goal_repeated', 'Gol. Gol. Gol.', True, 'repetition')
    tts('spanish_normal', 'El equipo prepara la siguiente jugada y la defensa está atenta.', False, 'spanish_normal')
    tts('similar_words', 'Golf, golpe, gorro, col, sol, color, gorila.', False, 'similar_words')
    tts('background_voices', 'La conversación continúa al fondo. Buenas tardes, ¿cómo estás?', False, 'background_tts')
    tts('background_mentions_goal', 'El comentarista dijo gol en la televisión.', True, 'speaker_intent_challenge', challenge=True)
    add('silence', [0.0] * (8 * RATE), False, 'silence', {'type': 'generated_zero_pcm'})
    add('noise', noise(8), False, 'seeded_noise', {'type': 'generated', 'seed': 714})
    add('game_noise', game_noise(8), False, 'synthetic_game_like_noise', {'type': 'generated', 'seed': 715})
    add('music', music(8), False, 'synthetic_music', {'type': 'original_procedural_arpeggio'})
    for name, background in [('goal_with_noise', noise(len(goal)/RATE)), ('goal_with_music', music(len(goal)/RATE))]:
        add(name, [a+b for a,b in zip(goal, background)], True, 'synthetic_mixture', {'type': 'generated_mix', 'speech_fixture': 'goal_normal'})
    manifest = {'version': 1, 'scope': 'owned_synthetic_offline_only', 'sample_rate': RATE,
                'generator_sha256': digest(pathlib.Path(__file__)), 'macos': platform.mac_ver()[0],
                'voice': args.voice, 'cases': cases,
                'limitations': ['No human shouts, real game audio or real background voices.',
                                'TTS may vary across macOS voice versions; WAV hashes identify the actual corpus.',
                                'No live audio tap, bounded queue or Show Control integration is exercised.',
                                'background_mentions_goal contains the keyword but is not an intentional command.']}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'PASS', 'scope': 'synthetic_corpus_only', 'cases': len(cases),
                      'seconds': sum(c['seconds'] for c in cases), 'manifest': str(output / 'manifest.json')}))


def keywords(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))
    return [word for word in re.findall(r'\b\w+\b', text) if re.fullmatch(r'go+l', word)]


def run(args):
    manifest_path = args.corpus.absolute()
    corpus = json.loads(manifest_path.read_text())
    if corpus.get('version') != 1 or corpus.get('scope') != 'owned_synthetic_offline_only':
        raise ValueError('This harness only accepts the controlled synthetic corpus')
    output = args.output.absolute()
    if output.exists():
        raise ValueError('Choose a new benchmark output directory')
    if not args.executable.is_file():
        raise ValueError('Explicit local recognizer executable required')
    executable = args.executable.resolve()
    model_record = None
    if args.backend == 'whisper':
        spec = json.loads((ROOT / 'scripts/voice-models.json').read_text())['whisper_cpp']
        if not args.model or not args.model.is_file():
            raise ValueError('No model installed; this script never downloads one')
        model_hash = digest(args.model)
        model_record = next((m for m in spec['models'] if m['sha256'] == model_hash and m['bytes'] == args.model.stat().st_size), None)
        if not model_record:
            raise ValueError('Model size/SHA-256 not in reviewed manifest')
    output.mkdir(parents=True)
    results = []
    load_start = os.getloadavg()
    for case in corpus['cases']:
        if not re.fullmatch(r'[a-z0-9_]{1,64}', case['id']):
            raise ValueError('Invalid fixture ID')
        path = (manifest_path.parent / case['file']).resolve()
        if path.parent != manifest_path.parent.resolve() or digest(path) != case['sha256']:
            raise ValueError('Corpus file escaped its directory or SHA-256 changed')
        samples = read_wav(path)
        duration = len(samples) / RATE
        target = output / case['id']
        if args.backend == 'whisper':
            command = [str(executable), '-m', str(args.model.resolve()), '-f', str(path),
                       '-l', 'es', '-t', str(args.threads), '-ng', '-otxt', '-of', str(target)]
        else:
            command = [str(executable), str(path), args.locale]
        stats = output / (case['id'] + '.time.txt')
        start = time.monotonic()
        row = {'id': case['id'], 'category': case['category'], 'challenge': case['challenge'],
               'expected_keyword': case['expected_keyword'], 'seconds': duration,
               'wav_sha256': case['sha256']}
        try:
            process = subprocess.Popen(['/usr/bin/time', '-l', '-o', str(stats), *command],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, start_new_session=True)
            try:
                stdout, stderr = process.communicate(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                # time(1) wraps the actual recognizer; terminate the whole group.
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise
            elapsed = time.monotonic() - start
            (output / (case['id'] + '.stderr.txt')).write_text(stderr)
            if args.backend == 'apple':
                recognition = json.loads(stdout)
                (output / (case['id'] + '.apple.json')).write_text(json.dumps(recognition, ensure_ascii=False, indent=2) + '\n')
                if recognition.get('status') != 'PASS':
                    raise RuntimeError(recognition.get('code', 'apple_recognition_failed'))
                text = recognition['text']
            else:
                text = target.with_suffix('.txt').read_text() if target.with_suffix('.txt').is_file() else ''
            if process.returncode:
                raise RuntimeError(f'recognizer_exit_{process.returncode}')
            matches = keywords(text)
            metrics = stats.read_text()
            rss = re.search(r'(\d+)\s+maximum resident set size', metrics)
            cpu_user = re.search(r'([\d.]+)\s+user', metrics)
            cpu_system = re.search(r'([\d.]+)\s+sys', metrics)
            events = [{'type': 'voice.keyword_candidate.v1', 'keyword': 'gol', 'source': 'offline_fixture',
                       'input_sha256': case['sha256'], 'candidate_index': index,
                       'command_executed': False} for index, _ in enumerate(matches)]
            row.update(status='PASS', text=text, detected_keyword=bool(matches), candidates=len(matches),
                       wall_ms=elapsed*1000, real_time_factor=elapsed/duration,
                       maximum_resident_bytes=int(rss.group(1)) if rss else None,
                       user_cpu_seconds=float(cpu_user.group(1)) if cpu_user else None,
                       system_cpu_seconds=float(cpu_system.group(1)) if cpu_system else None, events=events)
        except (subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError) as error:
            row.update(status='BLOCKED', error=str(error), wall_ms=(time.monotonic()-start)*1000)
        results.append(row)
        if row.get('error') in ['speech_permission_not_authorized', 'on_device_unavailable', 'locale_unavailable']:
            break
    valid = [r for r in results if r['status'] == 'PASS' and not r['challenge']]
    counts = {name: sum(bool(r['expected_keyword']) == actual and bool(r['detected_keyword']) == predicted for r in valid)
              for name, actual, predicted in [('tp', True, True), ('fn', True, False), ('fp', False, True), ('tn', False, False)]}
    negatives_seconds = sum(r['seconds'] for r in valid if not r['expected_keyword'])
    ordered_latencies = sorted(r['wall_ms'] for r in valid)
    report = {'version': 1, 'status': 'PARTIAL' if valid else 'BLOCKED', 'backend': args.backend,
              'scope': 'offline_whole_file_cold_process_synthetic', 'model': model_record,
              'executable_sha256': digest(executable), 'corpus_sha256': digest(manifest_path),
              'threads': args.threads if args.backend == 'whisper' else None, 'gpu': False if args.backend == 'whisper' else 'OS_managed',
              'macos': platform.mac_ver()[0], 'machine': platform.machine(),
              'load_average_start': load_start, 'load_average_end': os.getloadavg(),
              'counts': counts, 'results': results,
              'recall': counts['tp'] / (counts['tp'] + counts['fn']) if counts['tp'] + counts['fn'] else None,
              'precision': counts['tp'] / (counts['tp'] + counts['fp']) if counts['tp'] + counts['fp'] else None,
              'p95_wall_ms': ordered_latencies[math.ceil(len(ordered_latencies)*0.95)-1] if valid else None,
              'median_real_time_factor': statistics.median(r['real_time_factor'] for r in valid) if valid else None,
              'maximum_resident_bytes': max((r['maximum_resident_bytes'] or 0 for r in valid), default=0),
              'silence_nonempty_text': [r['id'] for r in valid if r['category'] == 'silence' and r['text'].strip()],
              'median_wall_ms': statistics.median(r['wall_ms'] for r in valid) if valid else None,
              'false_positive_clips_per_negative_hour': counts['fp'] / (negatives_seconds / 3600) if negatives_seconds else None,
              'limitations': corpus['limitations'] + ['Latency includes startup and model loading; it is not live keyword latency.',
                                                     'Short synthetic negatives cannot establish a production false-accept rate.',
                                                     'No speaker or intent classifier; keyword candidates must not directly trigger production.']}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['status', 'backend', 'counts', 'median_wall_ms']}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    generate = commands.add_parser('prepare')
    generate.add_argument('--output', type=pathlib.Path, required=True)
    generate.add_argument('--voice', default='Paulina')
    bench = commands.add_parser('run')
    bench.add_argument('--corpus', type=pathlib.Path, required=True)
    bench.add_argument('--output', type=pathlib.Path, required=True)
    bench.add_argument('--backend', choices=['whisper', 'apple'], required=True)
    bench.add_argument('--executable', type=pathlib.Path, required=True)
    bench.add_argument('--model', type=pathlib.Path)
    bench.add_argument('--threads', type=int, choices=range(1, 5), default=2)
    bench.add_argument('--locale', choices=['es-MX', 'es-ES'], default='es-MX')
    bench.add_argument('--timeout', type=int, choices=range(10, 121), default=90)
    args = parser.parse_args()
    if args.operation == 'prepare':
        prepare(args)
    else:
        run(args)


if __name__ == '__main__':
    main()

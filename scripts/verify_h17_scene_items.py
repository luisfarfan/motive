#!/usr/bin/env python3
"""Compile/run the scene ownership contract with real libobs and ASan.

Legacy FAIL is an expected reproduction, not a product/media acceptance pass.
No screen, audio device, output, permissions or global configuration is touched.
"""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    frameworks = ROOT / '.deps/OBS.app/Contents/Frameworks'
    source = ROOT / 'scripts/fixtures/h17_scene_items.c'
    binary = out / 'scene-items-test'
    command = ['clang', '-arch', 'arm64', '-g', '-O1', '-fsanitize=address',
               '-I', str(ROOT / '.deps/obs-studio-33.0.1/libobs'),
               '-I', str(ROOT / '.deps/simde-0.8.2'), '-I', str(ROOT / 'native'),
               str(source), '-F', str(frameworks), '-framework', 'libobs',
               '-Wl,-rpath,' + str(frameworks), '-o', str(binary)]
    subprocess.run(command, check=True, capture_output=True)
    runs = []
    for label, arguments, expected in [('legacy', ['--legacy'], 1), ('fixed', [], 0)]:
        result = subprocess.run([str(binary), *arguments], capture_output=True, text=True)
        (out / (label + '.log')).write_text(result.stdout + result.stderr)
        terminal = next((json.loads(line) for line in reversed(result.stdout.splitlines())
                         if line.startswith('{"status":')), {})
        valid = (result.returncode == expected and terminal.get('destroyed_sources') == 2
                 and terminal.get('status') == ('FAIL' if label == 'legacy' else 'PASS')
                 and 'ERROR: AddressSanitizer' not in result.stderr)
        runs.append({'label': label, 'exit': result.returncode, 'expected_exit': expected,
                     'terminal': terminal, 'status': 'PASS' if valid else 'FAIL'})
    report = {'status': 'PASS' if all(r['status'] == 'PASS' for r in runs) else 'FAIL',
              'scope': 'native ownership contract, not physical capture', 'runs': runs,
              'command': command, 'inputs': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in [source, ROOT / 'native/scene-items.h']}}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())

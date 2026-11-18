#!/usr/bin/env python3
"""Test extracted SCK admission branches through real libobs, without capture."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

from build_obs_capture import ARCHIVE_SHA, DEPS, PATCH, ADMISSION_PATCH, ROOT, SOURCE


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expressions(source):
    missing = re.search(r'if \(target_window == nil\) \{.*?return (.*?);', source, re.S).group(1)
    outputs = re.findall(r'if \(!did_add_output\) \{.*?return (.*?);', source, re.S)
    assert len(outputs) == 2
    match = re.search(r'if \((window.windowID == sc->window.*?)\) \{', source, re.S).group(1)
    for before, after in [('window.owningApplication.processID', 'owner_pid'),
                          ('sc->motive_window_owner_pid', 'expected_pid'),
                          ('window.windowID', 'window_id'), ('sc->window', 'expected_window')]:
        match = match.replace(before, after)
    # Only the extracted boolean expression is transformed into C; no function
    # with access to SCK/WindowServer is linked or executed by this contract.
    assert not re.search(r'[^a-zA-Z_0-9\s!=&|()]', match)
    return {'MISSING_WINDOW': missing, 'SCREEN_OUTPUT': outputs[0],
            'AUDIO_OUTPUT': outputs[1], 'WINDOW_MATCH': match}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    archive_path = DEPS / 'obs-studio-33.0.1.tar.gz'
    assert sha(archive_path) == ARCHIVE_SHA
    upstream = SOURCE / 'plugins/mac-capture'
    with tarfile.open(archive_path) as archive:
        for name in ('mac-sck-common.h', 'mac-sck-video-capture.m'):
            expected = archive.extractfile('obs-studio-33.0.1/plugins/mac-capture/' + name).read()
            assert (upstream / name).read_bytes() == expected
    patched = out / 'source'
    shutil.copytree(upstream, patched)
    for patch in (PATCH, ADMISSION_PATCH):
        subprocess.run(['patch', '-p1', '-i', str(patch)], cwd=patched, check=True, capture_output=True)
    template_path = ROOT / 'scripts/fixtures/h17_sck_admission.c'
    template = template_path.read_text()
    frameworks = DEPS / 'OBS.app/Contents/Frameworks'
    runs = []
    for label, folder, expected_exit in [('upstream', upstream, 1), ('patched', patched, 0)]:
        extracted = expressions((folder / 'mac-sck-video-capture.m').read_text())
        program = template
        for key, value in extracted.items():
            program = program.replace('@' + key + '@', value)
        path = out / (label + '.c')
        path.write_text(program)
        binary = out / label
        command = ['clang', '-arch', 'arm64', '-O1', '-g', '-fsanitize=address',
                   '-I', str(SOURCE / 'libobs'), '-I', str(DEPS / 'simde-0.8.2'),
                   '-I', str(ROOT / 'native'),
                   str(path), '-F', str(frameworks), '-framework', 'libobs',
                   '-Wl,-rpath,' + str(frameworks), '-o', str(binary)]
        compiled = subprocess.run(command, capture_output=True, text=True)
        (out / (label + '-build.log')).write_text(compiled.stdout + compiled.stderr)
        compiled.check_returncode()
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        (out / (label + '.log')).write_text(result.stdout + result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
        terminal = rows[-1]
        valid = (result.returncode == expected_exit and
                 terminal['status'] == ('PASS' if label == 'patched' else 'FAIL') and
                 terminal['failed_cases'] == (0 if label == 'patched' else 6) and
                 terminal['accepted'] == terminal['destroyed'] and
                 'ERROR: AddressSanitizer' not in result.stderr)
        runs.append({'label': label, 'status': 'PASS' if valid else 'FAIL',
                     'exit': result.returncode, 'extracted_expressions': extracted,
                     'cases': rows[:-1], 'terminal': terminal, 'command': command})
    # Compile the actual complete patched translation unit separately. This
    # validates the Objective-C API/struct wiring, without executing the module.
    command = ['clang', '-arch', 'arm64', '-mmacosx-version-min=13.0', '-fsyntax-only',
               '-Wno-deprecated-declarations', '-Wno-ignored-qualifiers',
               '-Wno-shorten-64-to-32', '-I', str(ROOT / 'native'), '-I', str(patched),
               '-I', str(SOURCE / 'libobs'), '-I', str(DEPS / 'simde-0.8.2'),
               str(patched / 'mac-sck-video-capture.m')]
    syntax = subprocess.run(command, capture_output=True, text=True)
    (out / 'syntax.log').write_text(syntax.stdout + syntax.stderr)
    report = {'status': 'PASS' if syntax.returncode == 0 and all(r['status'] == 'PASS' for r in runs) else 'FAIL',
              'scope': 'synthetic admission conditions, real libobs invalid-object contract; no physical capture',
              'physical_capture': 'NOT_EVALUATED', 'runs': runs,
              'syntax': {'status': 'PASS' if syntax.returncode == 0 else 'FAIL', 'command': command},
              'inputs': {str(p): sha(p) for p in [PATCH, ADMISSION_PATCH, template_path,
                  upstream / 'mac-sck-common.h', upstream / 'mac-sck-video-capture.m']}}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(out), 'status': report['status']}))
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())

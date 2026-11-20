#!/usr/bin/env python3
"""Build a pinned, clearly modified open-source Arkanoid in this worktree only.

Prerequisites are local sources in .deps; no installation or execution occurs.
This workload is a real simple 2D game, not evidence for heavier games.
"""
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_h14_collection import lock, save, require, digest


def main():
    held = lock()
    ray = ROOT / '.deps/raylib-6.0'
    upstream = ROOT / '.deps/h21-arkanoid-source'
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ray, text=True).strip()
            == 'dbc56a87da87d973a9c5baa4e7438a9d20121d28', 'Wrong raylib revision')
    require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ray),
            'Modified upstream raylib source')
    require(digest(upstream/'arkanoid.c') == '8b759b7a344cb0c0c768d456741fb9bfeec54f52c0615f0a65ddd5d7a843a218', 'Game source changed')
    app = ROOT / 'target/H21Arkanoid.app'
    require(not app.exists(), 'Preserve existing game build; choose a new candidate before rebuilding')
    evidence = ROOT / 'var/evidence/H21-game-build'
    evidence.mkdir(parents=True, exist_ok=False)
    commands = [['make', '-C', str(ray/'src'), '-j4', 'PLATFORM=PLATFORM_DESKTOP', 'RAYLIB_LIBTYPE=STATIC']]
    binary = app / 'Contents/MacOS/MotiveH21Arkanoid'
    binary.parent.mkdir(parents=True)
    fixtures = Path(__file__).parent
    commands.append(['clang', '-arch', 'arm64', '-O2', '-std=c11', '-I'+str(ray/'src'), '-I'+str(upstream),
        '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-deprecated-declarations',
        str(fixtures/'h21_game.c'), str(fixtures/'h21_game_window.m'), str(ray/'src/libraylib.a'),
        '-framework', 'OpenGL', '-framework', 'Cocoa', '-framework', 'IOKit', '-framework', 'CoreAudio',
        '-framework', 'CoreVideo', '-o', str(binary)])
    report = {'status': 'FAIL', 'lock': held, 'commands': [], 'upstream': json.loads((upstream/'sources.json').read_text())}
    try:
        for index, command in enumerate(commands):
            with (evidence/f'{index}.log').open('x') as log:
                result = subprocess.run(command, stdout=log, stderr=log)
            report['commands'].append({'argv': command, 'exit_code': result.returncode})
            require(result.returncode == 0, 'Game compilation failed; log retained')
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier':'local.motive.h21arkanoid', 'CFBundleExecutable':binary.name,
            'CFBundleName':'Motive H21 Arkanoid (modified)', 'CFBundlePackageType':'APPL',
            'CFBundleVersion':'1', 'NSHighResolutionCapable':True, 'LSAppNapIsDisabled':True}))
        resources = app/'Contents/Resources'; resources.mkdir()
        shutil.copy2(upstream/'LICENSE', resources/'Arkanoid-LICENSE')
        shutil.copy2(ray/'LICENSE', resources/'raylib-LICENSE')
        subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
        report['sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in
            (binary, fixtures/'h21_game.c', fixtures/'h21_game_window.m', upstream/'arkanoid.c', ray/'src/libraylib.a')}
        report['status'] = 'PASS'
    except Exception as error:
        report['error'] = repr(error)
    save(evidence/'report.json', report)
    print(json.dumps({'status':report['status'], 'error':report.get('error')}))
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())

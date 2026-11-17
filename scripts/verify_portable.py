#!/usr/bin/env python3
"""Verify an already-built portable app without launching Motive or capturing media."""
import argparse
import json
import os
import pathlib
import subprocess

from portable_support import audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=pathlib.Path)
    parser.add_argument('--report', type=pathlib.Path, required=True)
    parser.add_argument('--allow-unsigned', action='store_true')
    parser.add_argument('--smoke-tools', action='store_true', help='Run bundled FFmpeg version commands with a clean loader environment.')
    args = parser.parse_args()
    app = args.app.expanduser().absolute()
    result = audit(app, require_signature=not args.allow_unsigned)
    result['tool_smoke'] = []
    if args.smoke_tools:
        # No developer PATH or DYLD override may rescue missing bundle libraries.
        env = {key: value for key, value in os.environ.items() if not key.startswith('DYLD_')}
        env['PATH'] = '/usr/bin:/bin'
        for name in ['ffmpeg', 'ffprobe']:
            command = [str(app / 'Contents/MacOS' / name), '-version']
            try:
                p = subprocess.run(command, cwd='/', env=env, text=True, capture_output=True, timeout=15)
                result['tool_smoke'].append({'name': name, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
                if p.returncode:
                    result['issues'].append({'code': 'BUNDLED_TOOL_EXECUTION_FAILED', 'name': name})
            except (OSError, subprocess.TimeoutExpired) as e:
                result['issues'].append({'code': 'BUNDLED_TOOL_EXECUTION_FAILED', 'name': name, 'error': str(e)})
    result['static_status'] = 'PASS' if not result['issues'] else 'FAIL'
    result['motive_runtime_status'] = 'NOT_EVALUATED'
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'static_status': result['static_status'], 'issues': result['issues'], 'report': str(args.report)}))
    raise SystemExit(bool(result['issues']))


if __name__ == '__main__':
    main()

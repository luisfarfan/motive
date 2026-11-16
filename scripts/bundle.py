#!/usr/bin/env python3
"""Development bundle. Its libobs rpath still points to this checkout's .deps."""
import pathlib
import plistlib
import shutil
import subprocess
import argparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sign-identity', default='-', help='Existing local signing identity; default is ad hoc.')
args = parser.parse_args()
if subprocess.run(['pgrep', '-x', 'motive'], capture_output=True).returncode == 0:
    raise SystemExit('Close Motive before replacing its executable.')
subprocess.run(['cargo', 'build', '--locked'], cwd=ROOT, check=True)
app = ROOT / 'target/Motive.app/Contents'
(app / 'MacOS').mkdir(parents=True, exist_ok=True)
shutil.copy2(ROOT / 'target/debug/motive', app / 'MacOS/motive')
# The OBS muxer is located by the OBS plugin beside the executable.
shutil.copy2(ROOT / '.deps/OBS.app/Contents/MacOS/obs-ffmpeg-mux', app / 'MacOS/obs-ffmpeg-mux')
if not (app / 'Frameworks').exists():
    (app / 'Frameworks').symlink_to(ROOT / '.deps/OBS.app/Contents/Frameworks', target_is_directory=True)
with (app / 'Info.plist').open('wb') as f:
    plistlib.dump({
        'CFBundleIdentifier': 'local.motive.studio', 'CFBundleName': 'Motive',
        'CFBundleDisplayName': 'Motive', 'CFBundleExecutable': 'motive',
        'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '0.1.0',
        'CFBundleVersion': '1', 'LSMinimumSystemVersion': '15.0',
        'NSHighResolutionCapable': True, 'LSAppNapIsDisabled': True,
        'NSMicrophoneUsageDescription': 'Motive usa la entrada de audio que eliges para tu producción local.',
        'NSCameraUsageDescription': 'Motive usa únicamente la cámara que eliges para tu producción local.',
        'NSScreenCaptureUsageDescription': 'Motive captura únicamente la ventana elegida para tu producción.',
    }, f)
subprocess.run(['codesign', '--force', '--sign', args.sign_identity, str(app.parent)], check=True)
print(app.parent)

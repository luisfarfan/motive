#!/usr/bin/env python3
"""Build an owned AppKit window in a separate process for real capture tests."""
import pathlib, plistlib, subprocess
root=pathlib.Path(__file__).resolve().parents[1]
app=root/'target/MotiveFixture.app/Contents'
(app/'MacOS').mkdir(parents=True,exist_ok=True)
subprocess.run(['clang','-fobjc-arc','-framework','AppKit',str(root/'tests/window_fixture.m'),'-o',str(app/'MacOS/fixture')],check=True)
with (app/'Info.plist').open('wb') as f:
    plistlib.dump({'CFBundleIdentifier':'local.motive.fixture','CFBundleName':'MotiveFixture','CFBundleExecutable':'fixture','CFBundlePackageType':'APPL'},f)
subprocess.run(['codesign','--force','--sign','-',str(app.parent)],check=True)
print(app.parent)

#!/usr/bin/env python3
"""Build the owned H13 audio fixture; never launch it or change audio routing.

Run only while holding Motive's shared physical-test lock. Example (separately):
  target/H13AudioFixture.app/Contents/MacOS/MotiveAudioFixture --sequence

Sequence: 0-8 s tone, 8-12 zero buffers, 12-16 engine paused,
16-24 tone, 24-32 pulses (200 ms every sample-clock second), then tone.
Command-T/Z/P/B select tone/zero/pause/pulses; Command-S restarts sequence.
The window observes the audio render sample counter. Its redraw cadence is not
an independent media clock; compare drift and report display/output latency.
"""
import argparse
import pathlib
import plistlib
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sign-identity", default="-", help="Existing signing identity, or ad hoc (default).")
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[2]
    app = root / "target/H13AudioFixture.app"
    executable = app / "Contents/MacOS/MotiveAudioFixture"
    if subprocess.run(["pgrep", "-f", re.escape(str(executable))], capture_output=True).returncode == 0:
        raise SystemExit("Close this fixture before rebuilding it.")
    executable.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "clang", "-arch", "arm64", "-mmacosx-version-min=15.0", "-fobjc-arc", "-fblocks",
        "-Wall", "-Wextra", "-Wno-deprecated-declarations", "-framework", "AppKit",
        "-framework", "AVFoundation", str(pathlib.Path(__file__).with_name("h13_audio_app.m")),
        "-o", str(executable),
    ], check=True)
    with (app / "Contents/Info.plist").open("wb") as destination:
        plistlib.dump({
            "CFBundleIdentifier": "local.motive.audiofixture",
            "CFBundleName": "Motive Audio Fixture",
            "CFBundleDisplayName": "Motive Audio Fixture",
            "CFBundleExecutable": "MotiveAudioFixture",
            "CFBundlePackageType": "APPL",
            "CFBundleVersion": "1",
            "CFBundleShortVersionString": "1.0",
            "LSMinimumSystemVersion": "15.0",
            "NSHighResolutionCapable": True,
            "LSAppNapIsDisabled": True,
        }, destination)
    subprocess.run(["codesign", "--force", "--sign", args.sign_identity, str(app)], check=True)
    print(app)


if __name__ == "__main__":
    main()

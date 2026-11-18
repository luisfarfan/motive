"""Explicit test-only paths; never redirect product data or change HOME.

With no overrides the historical development paths are unchanged. Portable
tests require all three MOTIVE_TEST_* variables and the current user's real
runtime paths, so a verifier cannot back up one store while Motive uses another.
This resolver performs reads only; it never creates directories or launches apps.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import plistlib


ENV_KEYS = ('MOTIVE_TEST_APP', 'MOTIVE_TEST_DATA_ROOT', 'MOTIVE_TEST_RECORDINGS_ROOT')


@dataclass(frozen=True)
class VerificationPaths:
    root: Path
    app_bundle: Path
    app_executable: Path
    client_executable: Path
    data_root: Path
    recordings_root: Path
    portable: bool

    @property
    def socket(self):
        return self.data_root / 'run/motive.sock'

    @property
    def diagnostics_root(self):
        return (self.data_root.parent.parent / 'Logs/Motive'
                if self.portable else self.root / 'var/evidence')

    def lock_matches(self, text, development_milestone='H13'):
        if not self.portable:
            return development_milestone in text and str(self.root) in text
        try:
            owner = json.loads(text)
        except (ValueError, TypeError):
            return False
        return (isinstance(owner, dict) and owner.get('worktree') == str(self.root)
                and isinstance(owner.get('owner'), str)
                and bool({'H14', 'H15'} & set(owner['owner'].split())))

    def manifest(self):
        return {**{key: str(value) if isinstance(value, Path) else value
                   for key, value in self.__dict__.items()},
                'diagnostics_root': str(self.diagnostics_root)}


def _absolute(value, label):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError(f'{label} must be an absolute path without traversal')
    return path


def verification_paths(root, *, environ=None, home=None):
    root = Path(root)
    env = os.environ if environ is None else environ
    present = [key in env for key in ENV_KEYS]
    if not any(present):
        bundle = root / 'target/Motive.app'
        return VerificationPaths(root, bundle, bundle / 'Contents/MacOS/motive',
                                 root / 'target/debug/motive', root / 'var',
                                 root / 'var/recordings', False)
    if not all(present) or not all(env[key] for key in ENV_KEYS):
        raise ValueError('Portable verification requires all three nonempty MOTIVE_TEST_* paths')
    bundle, data, recordings = (_absolute(env[key], key) for key in ENV_KEYS)
    user = _absolute(str(Path.home() if home is None else home), 'HOME')
    expected_data = user / 'Library/Application Support/local.motive.studio'
    expected_recordings = user / 'Movies/Motive'
    if data != expected_data or recordings != expected_recordings:
        raise ValueError('Test data/recordings paths must match the portable runtime for the current HOME')
    # Runtime appends paths to HOME without remapping. Reject symlink aliases so
    # backup/restore checks and the installed app refer to the same directory.
    for path in (data, recordings):
        if path.resolve() != path or (path.exists() and not path.is_dir()):
            raise ValueError('Portable data/recordings paths must be direct directories')
    bundle = bundle.resolve(strict=True)
    if bundle.suffix != '.app' or not bundle.is_dir():
        raise ValueError('MOTIVE_TEST_APP must identify the portable .app bundle')
    marker = bundle / 'Contents/Resources/MotivePortable.json'
    if marker.is_symlink() or marker.stat().st_size > 4096:
        raise ValueError('Invalid portable bundle marker')
    value = json.loads(marker.read_text())
    if (not isinstance(value, dict) or set(value) != {'version', 'runtime_layout'} or type(value['version']) is not int
            or value != {'version': 1, 'runtime_layout': 'macos-portable-v1'}):
        raise ValueError('Unsupported portable bundle layout')
    info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
    if info.get('CFBundleIdentifier') != 'local.motive.studio' or info.get('CFBundleExecutable') != 'motive':
        raise ValueError('Unexpected Motive bundle identity')
    executable = (bundle / 'Contents/MacOS/motive').resolve(strict=True)
    if not executable.is_relative_to(bundle) or not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError('Portable executable must be executable and contained in its bundle')
    return VerificationPaths(root, bundle, executable, executable, data, recordings, True)

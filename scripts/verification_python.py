"""Read-only preflight for an explicitly selected existing verification venv."""
import json
import os
from pathlib import Path
import subprocess


PILLOW_SUITES = frozenset(('verify_h11_runtime.py', 'verify_h11_visuals.py',
                          'verify_h11_lifecycle.py', 'verify_h12_performance.py'))
PILLOW_VERSION = '12.0.0'
PROBE = '''import json, sys
import PIL
from PIL import Image, ImageChops
print(json.dumps({'executable':sys.executable,'prefix':sys.prefix,'base_prefix':sys.base_prefix,
                  'version':sys.version,'pillow_version':PIL.__version__,'pillow_file':PIL.__file__}))
'''


def verification_python(root, suites, selected=None):
    """No probe for legacy-only subsets; an empty selection means the full suite."""
    if suites and not PILLOW_SUITES.intersection(suites):
        return {'status': 'NOT_REQUIRED', 'requested': str(selected) if selected is not None else None}
    path = Path(selected) if selected is not None else Path(root) / 'var/verify-python/bin/python'
    if not path.is_absolute() or '..' in path.parts or not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError('Verification Python must be an absolute existing executable from an existing venv')
    # Preserve bin/python in argv. Resolving its final symlink to Homebrew's
    # interpreter would bypass the pyvenv.cfg and lose the selected environment.
    result = subprocess.run([str(path), '-I', '-B', '-c', PROBE], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise ValueError('Verification Python could not import the required Pillow modules (exit '
                         + str(result.returncode) + ')')
    metadata = json.loads(result.stdout)
    fields = {'executable', 'prefix', 'base_prefix', 'version', 'pillow_version', 'pillow_file'}
    if (not isinstance(metadata, dict) or set(metadata) != fields
            or any(not isinstance(value, str) or not value or len(value) > 4096 for value in metadata.values())):
        raise ValueError('Invalid verification Python provenance')
    prefix, base = Path(metadata['prefix']), Path(metadata['base_prefix'])
    if (not prefix.is_absolute() or not base.is_absolute() or prefix.resolve() == base.resolve()
            or prefix.resolve() != path.parent.parent.resolve()):
        raise ValueError('Verification Python must retain the explicitly selected venv prefix')
    if not Path(metadata['executable']).is_absolute() or Path(metadata['executable']).resolve() != path.resolve():
        raise ValueError('Verification Python executable identity differs')
    if (metadata['pillow_version'] != PILLOW_VERSION
            or not Path(metadata['pillow_file']).is_absolute()
            or not Path(metadata['pillow_file']).resolve().is_relative_to(prefix.resolve())):
        raise ValueError('Selected venv must contain Pillow ' + PILLOW_VERSION + ' without global site packages')
    return {'status': 'VERIFIED', 'requested': str(path), **metadata,
            'probe': 'isolated imports only; -B disables bytecode writes; no package installation'}

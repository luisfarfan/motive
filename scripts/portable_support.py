"""Read Mach-O dependency metadata and validate a closed macOS app layout."""
import hashlib
import json
import os
import pathlib
import plistlib
import subprocess

PLUGINS = ('obs-x264', 'obs-ffmpeg', 'obs-outputs', 'mac-capture', 'mac-avcapture',
           'obs-transitions', 'image-source', 'text-freetype2', 'mac-videotoolbox')
SYSTEM_PREFIXES = ('/System/Library/', '/usr/lib/')
MACHO_MAGIC = {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
               b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'}


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def macho(path):
    if path.is_symlink() or not path.is_file():
        return False
    with path.open('rb') as stream:
        return stream.read(4) in MACHO_MAGIC


def load_commands(path):
    output = subprocess.check_output(['otool', '-arch', 'arm64', '-l', str(path)], text=True)
    dependencies, rpaths, identifier = [], [], None
    kind = None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith('cmd '):
            kind = stripped[4:]
        elif kind == 'LC_RPATH' and stripped.startswith('path '):
            rpaths.append(stripped[5:].rsplit(' (offset ', 1)[0])
        elif kind in {'LC_LOAD_DYLIB', 'LC_LOAD_WEAK_DYLIB', 'LC_REEXPORT_DYLIB',
                      'LC_LOAD_UPWARD_DYLIB', 'LC_ID_DYLIB'} and stripped.startswith('name '):
            value = stripped[5:].rsplit(' (offset ', 1)[0]
            if kind == 'LC_ID_DYLIB':
                identifier = value
            else:
                dependencies.append(value)
    return {'dependencies': dependencies, 'rpaths': rpaths, 'id': identifier}


def architectures(path):
    return subprocess.check_output(['lipo', '-archs', str(path)], text=True).strip().split()


def inside(path, root):
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def expand_path(value, binary, contents):
    if value == '@loader_path' or value.startswith('@loader_path/'):
        return binary.parent / value.removeprefix('@loader_path').lstrip('/')
    if value == '@executable_path' or value.startswith('@executable_path/'):
        return contents / 'MacOS' / value.removeprefix('@executable_path').lstrip('/')
    return pathlib.Path(value)


def audit(app, require_signature=True):
    app = app.absolute()
    contents = app / 'Contents'
    issues, binaries = [], []
    required = ['MacOS/motive', 'MacOS/motive-credentials', 'MacOS/obs-ffmpeg-mux',
                'MacOS/ffmpeg', 'MacOS/ffprobe', 'Info.plist', 'Resources/MotivePortable.json',
                'Resources/ThirdParty/PROVENANCE.json', 'Frameworks/libobs-metal.dylib',
                'Frameworks/libobs.framework/libobs']
    required += [f'PlugIns/{n}.plugin/Contents/MacOS/{n}' for n in PLUGINS]
    for relative in required:
        if not (contents / relative).is_file():
            issues.append({'code': 'REQUIRED_FILE_MISSING', 'path': relative})
    try:
        marker = json.loads((contents / 'Resources/MotivePortable.json').read_text())
        if marker != {'version': 1, 'runtime_layout': 'macos-portable-v1'}:
            issues.append({'code': 'PORTABLE_MARKER_INVALID'})
        info = plistlib.loads((contents / 'Info.plist').read_bytes())
        for key, expected in [('CFBundleIdentifier', 'local.motive.studio'),
                              ('CFBundleExecutable', 'motive'), ('CFBundlePackageType', 'APPL')]:
            if info.get(key) != expected:
                issues.append({'code': 'BUNDLE_METADATA_INVALID', 'key': key})
        for key in ['NSMicrophoneUsageDescription', 'NSCameraUsageDescription', 'NSScreenCaptureUsageDescription']:
            if not isinstance(info.get(key), str) or not info[key].strip():
                issues.append({'code': 'PRIVACY_DESCRIPTION_MISSING', 'key': key})
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        issues.append({'code': 'BUNDLE_METADATA_UNREADABLE', 'error': str(error)})
    for path in app.rglob('*'):
        relative = str(path.relative_to(app))
        if path.is_symlink():
            if os.path.isabs(os.readlink(path)) or not inside(path, app):
                issues.append({'code': 'EXTERNAL_OR_BROKEN_SYMLINK', 'path': relative})
            continue
        if not macho(path):
            continue
        metadata = load_commands(path)
        arch = architectures(path)
        if arch != ['arm64']:
            issues.append({'code': 'ARCHITECTURE_NOT_ARM64_ONLY', 'path': relative, 'architectures': arch})
        for rpath in metadata['rpaths']:
            if not rpath.startswith(('@loader_path', '@executable_path')) or not inside(expand_path(rpath, path, contents), app):
                issues.append({'code': 'EXTERNAL_RPATH', 'path': relative, 'rpath': rpath})
        for dependency in metadata['dependencies']:
            if dependency.startswith(SYSTEM_PREFIXES):
                continue
            candidates = []
            if dependency.startswith('@rpath/'):
                candidates = [expand_path(rp, path, contents) / dependency[7:] for rp in metadata['rpaths']]
            elif dependency.startswith(('@loader_path/', '@executable_path/')):
                candidates = [expand_path(dependency, path, contents)]
            if not any(candidate.is_file() and inside(candidate, app) for candidate in candidates):
                issues.append({'code': 'DEPENDENCY_OUTSIDE_APP_OR_MISSING', 'path': relative, 'dependency': dependency})
        binaries.append({'path': relative, 'sha256': sha256(path), 'architectures': arch, **metadata})
    if not binaries:
        issues.append({'code': 'NO_MACHO_EXECUTABLES'})
    forbidden = ('Qt', 'Chromium Embedded Framework', 'obs-browser', 'OBS Helper', 'Sparkle', 'obs-frontend')
    for path in contents.rglob('*'):
        if any(path.name.startswith(prefix) for prefix in forbidden):
            issues.append({'code': 'UNEXPECTED_COMPONENT', 'path': str(path.relative_to(app))})
    signature = {'requested': require_signature}
    if require_signature:
        result = subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)],
                                text=True, capture_output=True)
        signature.update(returncode=result.returncode, stderr=result.stderr.strip())
        if result.returncode:
            issues.append({'code': 'CODESIGN_VERIFY_FAILED'})
        identifiers = {}
        for name, expected in [('motive', 'local.motive.studio'), ('motive-credentials', 'local.motive.credentials')]:
            details = subprocess.run(['codesign', '--display', '--verbose=4', str(contents / 'MacOS' / name)],
                                     text=True, capture_output=True)
            identifier = next((line.removeprefix('Identifier=') for line in details.stderr.splitlines()
                               if line.startswith('Identifier=')), None)
            identifiers[name] = identifier
            if details.returncode or identifier != expected:
                issues.append({'code': 'SIGNING_IDENTIFIER_MISMATCH', 'path': name})
        signature['identifiers'] = identifiers
    return {'schema_version': 1, 'app': str(app), 'static_status': 'PASS' if not issues else 'FAIL',
            'issues': issues, 'binaries': binaries, 'signature': signature,
            'limits': ['Static closure does not prove runtime plugin loading, capture, media or macOS permissions.',
                       'Notarization and installation on another Mac require their own verification.']}


def thin_arm64(path):
    arch = architectures(path)
    if 'arm64' not in arch:
        raise RuntimeError(f'No arm64 slice: {path}')
    if arch == ['arm64']:
        return
    temporary = path.with_name(path.name + '.arm64-part')
    subprocess.run(['lipo', str(path), '-thin', 'arm64', '-output', str(temporary)], check=True)
    temporary.chmod(path.stat().st_mode)
    temporary.replace(path)


def fix_rpaths(path, contents):
    metadata = load_commands(path)
    for rpath in dict.fromkeys(metadata['rpaths']):
        subprocess.run(['install_name_tool', '-delete_rpath', rpath, str(path)], check=True)
    relative = os.path.relpath(contents / 'Frameworks', path.parent)
    rpath = '@loader_path' if relative == '.' else '@loader_path/' + relative
    subprocess.run(['install_name_tool', '-add_rpath', rpath, str(path)], check=True)
    if metadata['id'] is not None:
        relative = path.relative_to(contents / 'Frameworks')
        subprocess.run(['install_name_tool', '-id', '@rpath/' + str(relative), str(path)], check=True)

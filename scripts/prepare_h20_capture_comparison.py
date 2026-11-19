#!/usr/bin/env python3
"""Clone a private portable candidate and replace only its mac-capture module.

This is a module comparison under the same Motive/libobs owner, not an OBS Qt
application comparison. Does not launch capture or modify the source bundle.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from portable_support import audit, fix_rpaths, macho, sha256
from verify_h14_collection import ROOT, lock, require, save


def inventory(app):
    return {str(p.relative_to(app)): sha256(p) for p in app.rglob('*') if macho(p)}


def unsigned_digest(path):
    # Re-signing the outer bundle changes its executable's embedded signature
    # because the Resources envelope changed. Compare exact stripped bytes too.
    with tempfile.TemporaryDirectory(prefix='h20-code-identity-') as temporary:
        copy = Path(temporary) / 'motive'
        shutil.copy2(path, copy)
        subprocess.run(['codesign', '--remove-signature', str(copy)], check=True)
        return sha256(copy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock-held', action='store_true', required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--variant', choices=['upstream', 'observed', 'admission', 'motive'], required=True)
    args = parser.parse_args()
    lock()
    base = args.base.resolve(strict=True)
    out = args.output.absolute()
    require(out.is_relative_to(ROOT / 'target/h20') and out.suffix == '.app' and not out.exists(),
            'Use a new private target/h20/*.app path')
    require(audit(base)['static_status'] == 'PASS', 'Base portable closure failed')
    build = ROOT / ('target/mac-capture-h14' if args.variant == 'motive'
                    else 'target/h20/mac-capture-' + args.variant)
    manifest = json.loads((build / 'manifest.json').read_text())
    module = build / 'mac-capture.so'
    require(manifest['built'] and manifest['variant'] == args.variant
            and manifest['module_sha256'] == sha256(module), 'Module differs from build inventory')
    subprocess.run(['cp', '-cR', str(base), str(out)], check=True)
    contents = out / 'Contents'
    relative = 'Contents/PlugIns/mac-capture.plugin/Contents/MacOS/mac-capture'
    target = out / relative
    shutil.copy2(module, target)
    fix_rpaths(target, contents)
    subprocess.run(['codesign', '--force', '--sign', '-', str(target)], check=True)
    record = {**manifest, 'base_bundle': str(base), 'bundled_module_sha256': sha256(target),
              'comparison_scope': 'mac-capture module under identical Motive owner, not OBS Qt UI',
              'original_module_sha256': sha256(base / relative)}
    save(contents / 'Resources/H20CaptureComparison.json', record)
    provenance = contents / 'Resources/ThirdParty/PROVENANCE.json'
    value = json.loads(provenance.read_text())
    value['patched_modules']['mac-capture'] = {'sha256': manifest['module_sha256'],
        'variant': args.variant, 'patches': manifest['patches'],
        'comparison_manifest': 'Resources/H20CaptureComparison.json'}
    save(provenance, value)
    subprocess.run(['codesign', '--force', '--sign', '-', str(contents / 'PlugIns/mac-capture.plugin')], check=True)
    subprocess.run(['codesign', '--force', '--sign', '-', str(out)], check=True)
    before, after = inventory(base), inventory(out)
    require(before.keys() == after.keys(), 'Native inventory changed unexpectedly')
    differences = [name for name in before if before[name] != after[name]]
    owner = 'Contents/MacOS/motive'
    owner_before, owner_after = unsigned_digest(base / owner), unsigned_digest(out / owner)
    require(all(name in (relative, owner) for name in differences)
            and owner_before == owner_after, 'Unrelated native code differs')
    result = audit(out)
    result.update(variant=args.variant, base_inventory=before, candidate_inventory=after,
                  native_differences=differences, unsigned_owner_sha256=owner_after,
                  owner_signature_change='Bundle resource envelope; stripped executable bytes identical',
                  physical_result='NOT_RUN')
    save(out.with_suffix('.comparison.json'), result)
    require(result['static_status'] == 'PASS', 'Candidate closure failed')
    print(json.dumps({'app': str(out), 'variant': args.variant, 'native_differences': differences}))


if __name__ == '__main__':
    main()

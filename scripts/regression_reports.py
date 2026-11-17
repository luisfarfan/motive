"""Pure primary-report gate for the unchanged H1–H12 regression runners.

Only freshly retained report names are eligible. This does not recursively
interpret protocol failures: those are often the subject of a successful test.
Exit status, native quiescence and each runner's existing assertions still apply.
"""
from pathlib import PurePosixPath


PRIMARY_REPORTS = {
    'verify_control.py': 'control-integration.json',
    'verify_control_delivery.py': 'h9-control-delivery.json',
    'verify_h1.py': 'h1-acceptance.json',
    'verify_scenes.py': 'scene-acceptance.json',
    'verify.py': 'acceptance.json',
    'verify_encoding.py': 'encoding-comparison.json',
    'verify_encoding_fallback.py': 'encoding-fallback.json',
    'verify_output_recovery.py': 'output-recovery.json',
    'verify_rtmp.py': 'h7-rtmp.json',
    'verify_rtmps.py': 'h7-rtmps.json',
    'verify_connect_stop.py': 'h7-connect-stop.json',
    'verify_vt_stop.py': 'h7-vt-stop.json',
    'verify_profiles_restart.py': 'h7-profiles-restart.json',
    'verify_h8_lifecycle.py': 'h8-lifecycle.json',
    'verify_h8_keychain.py': 'h8-keychain.json',
    'verify_h9_transitions.py': 'h9-transitions.json',
    'verify_h9_faults.py': 'h9-faults.json',
    'verify_h10_audio.py': 'h10-pilot.json',
    'verify_h10_mixer.py': 'h10-mixer.json',
    'verify_h11_runtime.py': 'h11-runtime.json',
    'verify_h11_visuals.py': 'h11-visuals.json',
    'verify_h11_lifecycle.py': 'h11-lifecycle-*/report.json',
    'verify_h12_performance.py': 'h12-performance-*/report.json',
}
FAILURE_FIELDS = ('error', 'cleanup_error', 'cleanup_errors',
                  'cleanup_required_reference', 'reopen_error', 'app_sha256_error')


def primary_report_path(suite, fresh_paths):
    """Choose exactly one known primary, never the newest historical report."""
    if suite not in PRIMARY_REPORTS:
        raise ValueError('Unknown regression suite: ' + suite)
    pattern = PRIMARY_REPORTS[suite]
    candidates = []
    for name in fresh_paths:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name:
            raise ValueError('Noncanonical retained evidence path')
        if '*' not in pattern:
            matches = name == pattern
        else:
            prefix = pattern.split('*', 1)[0]
            matches = (len(path.parts) == 2 and path.name == 'report.json'
                       and path.parts[0].startswith(prefix)
                       and path.parts[0][len(prefix):].isascii()
                       and path.parts[0][len(prefix):].isdigit())
        if matches:
            candidates.append(name)
    if len(candidates) != 1:
        raise ValueError('Expected exactly one fresh primary report for ' + suite
                         + '; found ' + str(len(candidates)))
    return candidates[0]


def primary_acceptance(document, expected_app_sha256=None):
    """Validate the primary's acknowledgement and explicit top-level failures."""
    issues = []
    if not isinstance(document, dict):
        issues.append({'code': 'PRIMARY_NOT_OBJECT'})
    else:
        if document.get('ok') is not True:
            issues.append({'code': 'PRIMARY_NOT_SUCCESS', 'field': 'ok'})
        for field in FAILURE_FIELDS:
            if field not in document or document[field] is None:
                continue
            if field == 'cleanup_errors' and document[field] == []:
                continue
            # Do not include error contents or an opaque cleanup reference in the
            # assessment. The original private evidence remains authoritative.
            issues.append({'code': 'PRIMARY_REPORTED_FAILURE', 'field': field})
        if expected_app_sha256 is not None:
            for field in ('app_sha256', 'bundle_sha256'):
                if field in document and document[field] != expected_app_sha256:
                    issues.append({'code': 'PRIMARY_BUILD_MISMATCH', 'field': field})
    return {'status': 'FAIL' if issues else 'PASS', 'issues': issues,
            'scope': 'Fresh primary acknowledgement and reported cleanup; child exit and owner barriers remain required.'}

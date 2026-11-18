"""Cross-process focus evidence for an owned fixture; no synthesized confirmation."""
import math


def corroborate(probe, fixture, *, fixture_pid, window_id, expected_pid):
    """Require independently sampled system focus AND contemporaneous fixture state.

    Both processes name NSProcessInfo.systemUptime. App inactivity alone cannot
    identify the active application. Missing/stale/contradictory evidence fails
    closed. This checks focus metadata, never capture freshness.
    """
    def finite(value):
        return type(value) in (float, int) and math.isfinite(value)

    before, after = probe.get('before_s'), probe.get('after_s')
    timestamp = fixture.get('uptime_seconds')
    window = probe.get('window') or {}
    identities = (probe.get('version') == 1
                  and probe.get('clock') == 'NSProcessInfo.systemUptime'
                  and probe.get('observer_pid') not in (None, fixture_pid, expected_pid)
                  and probe.get('expected_pid') == expected_pid
                  and probe.get('window_id') == window_id
                  and window.get('owner_pid') == fixture_pid
                  and fixture.get('pid') == fixture_pid
                  and fixture.get('window_id') == window_id)
    timing = (all(finite(v) for v in (before, after, timestamp))
              and 0 <= after-before <= .5 and before-1.5 <= timestamp <= after)
    expected_active = expected_pid == fixture_pid
    agrees = (probe.get('frontmost_pid') == expected_pid
              and probe.get('frontmost_terminated') is False
              and fixture.get('app_active') is expected_active
              and fixture.get('key_window') is expected_active)
    return {'status': 'PASS' if identities and timing and agrees else 'BLOCKED',
            'reason': None if identities and timing and agrees else 'HUMAN_ACTION_REQUIRED',
            'identity_valid': identities, 'contemporaneous': timing,
            'system_and_fixture_agree': agrees, 'proves_published_pixels': False}

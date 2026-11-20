"""Separate an explicitly collected microphone clipping warning from failures.

The warning remains a failed audio-quality gate. This only allows a diagnostic
session to measure output continuity without aborting at that warning.
"""


def classify_issues(issues, microphone_id, collect_clipping=False):
    collected, blockers = [], []
    for issue in issues:
        if (collect_clipping and issue.get('input_id') == microphone_id
                and issue.get('code') == 'AUDIO_INPUT_CLIPPING'
                and issue.get('severity') == 'warning'
                and issue.get('recovery') == 'reduce_device_gain'):
            collected.append(issue)
        else:
            blockers.append(issue)
    return collected, blockers

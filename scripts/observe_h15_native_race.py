#!/usr/bin/env python3
"""Read-only observation of one real stock450 GPUI goal and gain edit.

Caller owns the app, physical lock, tone, UI actions and media cleanup. This
observer never configures rules, dispatches actions or supplies a UI origin.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import traceback

from verify_h13_outputs import Client, APP
from verify_h14_collection import lock
from h14_show_helpers import counter_value
from h14_ui_concurrency_helpers import pending_evidence, ui_gain_edit, classify_result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', required=True, type=int)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    lock()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'FAIL', 'gate': {'status': 'NOT_OBSERVED'}, 'read_only': True,
              'binary_sha256': hashlib.sha256(Path(APP).read_bytes()).hexdigest()}
    client = Client(args.output)
    try:
        initial = client.state()
        assert initial['pid'] == args.pid
        sc = initial['show_control']
        assert sc['armed'] and sc['bindings_current'] and not sc['jobs']
        inputs = initial['audio_mixer']['store']['inputs']
        assert len(inputs) == 1 and inputs[0]['source'] == {'kind': 'tone'}
        assert inputs[0]['gain_db'] == -12 and not inputs[0]['muted']
        assert initial['outputs']['recording']['phase'] == 'active'
        attempt = initial['outputs']['recording']['attempt_id']
        report['initial'] = initial
        tone, session, baseline = inputs[0]['id'], sc['session'], counter_value(initial)
        before = edit = job = None
        print('READY_FOR_REAL_UI_GOAL_AND_GAIN', flush=True)
        deadline = time.monotonic() + 60
        with (args.output/'observations.jsonl').open('w') as log:
            while time.monotonic() < deadline:
                state = client.state()
                assert state['pid'] == args.pid and state['show_control']['session'] == session
                assert state['outputs']['recording']['attempt_id'] == attempt
                assert state['outputs']['recording']['phase'] == 'active'
                log.write(json.dumps({'monotonic': time.monotonic(), 'state': state})+'\n')
                jobs = state['show_control']['jobs']
                assert len(jobs) <= 1
                if jobs:
                    job = jobs[0]
                    assert job['rule_id'] == 'deck-goal'
                    assert re.fullmatch(r'ui-'+str(args.pid)+r'-[1-9][0-9]*', job['event_id'])
                    pending = pending_evidence(state, job, session, tone, 450)
                    if pending:
                        if before is None and pending['job_state'] == 'awaiting_completion' and pending['gain_db'] == -12:
                            before = pending
                        if before and edit is None and ui_gain_edit(pending):
                            edit = pending
                    if job['state'] in ('completed', 'needs_reconciliation'):
                        current = state['audio_mixer']['store']['inputs'][0]
                        if current['gain_db'] == 0:
                            report['gate'] = classify_result(before, edit, job, state, baseline)
                            break
                time.sleep(.01)
            report.update(pending_before=before, pending_after_ui=edit, final=state)
            if job:
                # Observe bounded native quiescence without reconciling or replaying.
                end = time.monotonic() + 8
                while time.monotonic() < end:
                    state = client.state()
                    log.write(json.dumps({'monotonic': time.monotonic(), 'state': state})+'\n')
                    if report['gate']['status'] == 'PASS':
                        assert counter_value(state) == baseline
                        assert state['show_control']['jobs'][0]['state'] == 'needs_reconciliation'
                    time.sleep(.05)
                report['after_quiescence'] = state
        report['status'] = 'PARTIAL' if report['gate']['status'] != 'FAIL' else 'FAIL'
    except Exception as exc:
        report.update(error=str(exc), traceback=traceback.format_exc())
    finally:
        client.close()
        (args.output/'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'status': report['status'], 'gate': report['gate']['status']}))


if __name__ == "__main__":
    main()

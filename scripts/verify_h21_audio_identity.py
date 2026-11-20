#!/usr/bin/env python3
"""Actual application exit/relaunch, no automatic follow, explicit idle recovery.

Caller supplies a fresh signed owner and the canonical physical lock. Uses the
owned H13 audio fixture and decodes a recording after cold reconnection. This
does not inject LaunchServices absence or prove SCStream callback lifetime.
"""
import argparse
import hashlib
from pathlib import Path
import shutil

from verify_h13_system_audio import Run, input_state


def main():
    args = argparse.Namespace(stage=['idle_identity_recovery'], lock_dir=None,
                              fixture_snapshots=False, microphone_id=None)
    run = Run(args)
    run.report['scope'] = __doc__
    source = Path(__file__)
    run.report['identity_verifier_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    shutil.copy2(source, run.path/source.name)
    shutil.copy2(source.with_name('verify_h13_system_audio.py'), run.path/'verify_h13_system_audio.py')
    try:
        run.setup()
        before = run.client.state()
        assert all(not output['native_busy'] for output in before['outputs'].values())
        old = input_state(before, run.system)
        old_pid = run.fixture.pid
        identity = old['application_identity']
        assert identity['expected_pid'] == old_pid
        assert identity['process_probe'] == 'observed'
        assert identity['process_generation_matches'] and identity['process_executable_matches']
        run.stop_fixture()
        missing = run.wait(lambda state: input_state(state, run.system)['phase'] == 'failed')
        run.launch_fixture()
        assert run.fixture.pid != old_pid
        run.wait_fixture_selectable()
        replaced = run.client.state()
        pinned = input_state(replaced, run.system)
        assert pinned['phase'] == 'failed' and pinned['instance_id'] == old['instance_id']
        assert pinned['application_identity']['expected_pid'] == old_pid
        assert all(not output['native_busy'] for output in replaced['outputs'].values())
        run.client.call('reconnect_audio_input', input_id=run.system)
        recovered = run.wait(lambda state: input_state(state, run.system)['phase'] == 'ready')
        current = input_state(recovered, run.system)
        assert current['instance_id'] != old['instance_id']
        identity = current['application_identity']
        assert identity['expected_pid'] == run.fixture.pid
        assert identity['process_probe'] == 'observed'
        assert identity['process_generation_matches'] and identity['process_executable_matches']
        run.report['identity_recovery'] = dict(before=before, missing=missing,
            replaced=replaced, recovered=recovered, old_pid=old_pid, new_pid=run.fixture.pid)
        run.pilot()
        run.report['ok'] = True
    except BaseException as error:
        run.report['error'] = repr(error)
        raise
    finally:
        run.cleanup()
        print(run.path/'report.json', flush=True)


if __name__ == '__main__':
    main()

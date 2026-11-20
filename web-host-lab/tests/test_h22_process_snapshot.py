import dataclasses
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from h22_process_snapshot import NativeSnapshot
from test_supervisor import SupervisorTests, module


class NativeObserverSupervisorTests(SupervisorTests):
    # Run the same real exit/tree/deadline/RSS/crash/error-cleanup suite with the
    # alternative observer. These are owned Python children, not CEF capacity.
    def supervisor(self, **kw):
        return module.Supervisor(self.root, process_snapshot=NativeSnapshot(module), **kw)

    def test_own_metadata_matches_public_identity(self):
        observer = NativeSnapshot(module)
        process = observer()[os.getpid()]
        self.assertEqual(process.parent, os.getppid())
        self.assertEqual(process.group, os.getpgrp())
        self.assertEqual(process.birth, module.birth_identity(os.getpid()))
        self.assertGreater(process.rss_kib, 0)
        self.assertIsNone(process.cpu_percent)

    def test_suspend_clock_discontinuity_fails_instead_of_hiding_idle_gap(self):
        observer=NativeSnapshot(module)
        offset=observer.initial_upper+100_000_000
        observer.clock_offset=lambda:(offset,offset+1000)
        with self.assertRaisesRegex(RuntimeError,'SYSTEM_SUSPEND_INTERRUPTION'):observer()
        self.assertGreaterEqual(observer.report()['suspend_elapsed_lower_bound_ms'],100)

    def test_suspend_failure_still_reaps_real_owned_child(self):
        observer=NativeSnapshot(module)
        def disrupted():
            if observer.calls:
                offset=observer.initial_upper+100_000_000
                observer.clock_offset=lambda:(offset,offset+1000)
            return observer()
        supervisor=module.Supervisor(self.root,process_snapshot=disrupted)
        with self.assertRaisesRegex(RuntimeError,'SYSTEM_SUSPEND_INTERRUPTION'):
            supervisor.run([sys.executable,'-c','import time;time.sleep(30)'])
        self.assertEqual(supervisor.last_report['error_code'],'SYSTEM_SUSPEND_INTERRUPTION')
        self.assertTrue(supervisor.last_report['final_cleanup_observed_tree'])

    def test_service_role_allowlist_does_not_leak_unknown_argument(self):
        self.assertEqual(module.chromium_role('--type=utility --utility-sub-type=data_decoder.mojom.DataDecoderService','helper'),'data_decoder_service')
        self.assertEqual(module.chromium_role('--type=utility --utility-sub-type=secret.private.payload','helper'),'utility')

    def test_owned_missing_rss_fails_closed_and_cleans(self):
        observer = NativeSnapshot(module)
        def missing():
            return {pid: dataclasses.replace(p, rss_kib=-1) for pid,p in observer().items()}
        s = module.Supervisor(self.root, process_snapshot=missing)
        with self.assertRaisesRegex(RuntimeError, 'OWNED_RSS_UNAVAILABLE'):
            s.run([sys.executable, '-c', 'import time;time.sleep(30)'])
        self.assertTrue(s.last_report['final_cleanup_observed_tree'])


if __name__ == '__main__': unittest.main()

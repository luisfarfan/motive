import importlib.util
import ctypes
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

LAB = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('h19_supervision', LAB / 'poc/browser-host/supervisor.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class H19Supervision(unittest.TestCase):
    def test_task_info_matches_public_sdk_and_own_process(self):
        with tempfile.TemporaryDirectory(dir=LAB / '.cache') as directory:
            source, binary = Path(directory) / 'layout.c', Path(directory) / 'layout'
            source.write_text('#include <sys/proc_info.h>\n#include <stddef.h>\n#include <stdio.h>\n'
                              'int main(void){printf("%zu %zu", sizeof(struct proc_taskinfo),'
                              'offsetof(struct proc_taskinfo,pti_threadnum));}\n')
            subprocess.run(['/usr/bin/xcrun', 'clang', str(source), '-o', str(binary)], check=True, capture_output=True)
            sizes = list(map(int, subprocess.check_output([str(binary)], text=True).split()))
            self.assertEqual(sizes, [ctypes.sizeof(module.ProcTaskInfo), module.ProcTaskInfo.threadnum.offset])
        process = module.Process(os.getpid(), 0, 0, 0, 0, module.birth_identity(os.getpid()), 'R')
        usage = module.owned_resource_usage(process)
        self.assertGreater(usage['virtual_bytes'], usage['resident_bytes'])
        self.assertGreater(usage['thread_count'], 0)
        self.assertIsNone(usage['unique_physical_bytes'])

    def test_role_whitelist_does_not_emit_raw_arguments(self):
        self.assertEqual(module.chromium_role('owned Helper --type=utility --utility-sub-type=network.mojom.NetworkService --token=PRIVATE', 'helper_unspecified'), 'network_service')
        self.assertEqual(module.chromium_role('owned --type=gpu-process', 'helper_unspecified'), 'gpu')
        self.assertEqual(module.chromium_role('owned --type=unknown --url=PRIVATE', 'helper_unspecified'), 'helper_unspecified')
        self.assertEqual(module.chromium_role('owned --type=utility --utility-sub-type=unknown', 'helper_unspecified'), 'utility')

    def test_birth_race_rejects_role_lookup(self):
        process = module.Process(os.getpid(), 0, 0, 0, 0, (0, 0), 'R')
        self.assertEqual(module.owned_chromium_role(process, 'browser_host'), 'browser_host')

    def test_real_sampled_overshoot_and_cleanup_are_retained(self):
        with tempfile.TemporaryDirectory(dir=LAB / '.cache') as directory:
            supervisor = module.Supervisor(Path(directory), deadline_seconds=2,
                                           rss_limit_kib=1, sample_capacity=4096,
                                           inspect_roles=True)
            report = supervisor.run([sys.executable, '-c', 'import time; time.sleep(5)'])
            self.assertEqual(report['reason'], 'rss_limit')
            self.assertGreater(report['rss_budget']['observed_overshoot_kib'], 0)
            self.assertIsNotNone(report['rss_budget']['first_exceedance'])
            self.assertTrue(any(s['phase'] == 'cleanup' for s in report['samples']))
            self.assertEqual(report['sample_retention']['dropped_oldest'], 0)
            self.assertTrue(report['final_cleanup_observed_tree'])

    def test_sample_capacity_is_bounded(self):
        with tempfile.TemporaryDirectory(dir=LAB / '.cache') as directory:
            for capacity in (0, 8193, True):
                with self.assertRaisesRegex(ValueError, 'CAPACITY'):
                    module.Supervisor(Path(directory), sample_capacity=capacity)


if __name__ == '__main__':
    unittest.main()

import ctypes
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('motive_resource_supervisor', ROOT / 'poc/browser-host/supervisor.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ResourceSamplerTests(unittest.TestCase):
    def test_ctypes_layout_matches_installed_public_sdk(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache') as root:
            source, binary = Path(root) / 'layout.c', Path(root) / 'layout'
            source.write_text('#include <sys/resource.h>\n#include <stddef.h>\n#include <stdio.h>\n'
                              'int main(void){printf("%zu %zu %zu %zu",sizeof(struct rusage_info_v0),'
                              'offsetof(struct rusage_info_v0,ri_user_time),offsetof(struct rusage_info_v0,ri_phys_footprint),'
                              'offsetof(struct rusage_info_v0,ri_proc_start_abstime));}\n')
            subprocess.run(['/usr/bin/xcrun', 'clang', str(source), '-o', str(binary)], check=True, capture_output=True)
            observed = list(map(int, subprocess.check_output([str(binary)], text=True).split()))
            self.assertEqual(observed, [ctypes.sizeof(module.RusageInfoV0), module.RusageInfoV0.user_time.offset,
                                      module.RusageInfoV0.phys_footprint.offset, module.RusageInfoV0.proc_start_abstime.offset])

    def test_public_cpu_unit_matches_python_process_time_nanoseconds(self):
        birth = module.birth_identity(os.getpid())
        process = module.Process(os.getpid(), os.getppid(), os.getpgrp(), 0, 0, birth, 'R')
        before = module.owned_resource_usage(process)
        cpu_start = time.process_time_ns()
        while time.process_time_ns() - cpu_start < 100_000_000:
            pass
        cpu_end = time.process_time_ns()
        after = module.owned_resource_usage(process)
        delta = after['cpu_time_ns'] - before['cpu_time_ns']
        self.assertGreater(delta, 90_000_000)
        self.assertLess(abs(delta - (cpu_end - cpu_start)), 20_000_000)
        self.assertGreater(after['phys_footprint_bytes'], 0)

    def test_wrong_birth_is_rejected_before_read(self):
        process = module.Process(os.getpid(), 0, 0, 0, 0, (0, 0), 'R')
        self.assertIsNone(module.owned_resource_usage(process))

    def test_missing_and_reused_identity_do_not_create_fake_cpu_zero(self):
        sampler = module.ResourceSampler()
        p = module.Process(123, 0, 0, 0, 0, (1, 2), 'R')
        def row(total, start=3):
            return {'role': 'owned_python', 'proc_start_abstime': start, 'cpu_time_ns': total,
                    'phys_footprint_bytes': 1024}
        with patch.object(module, 'owned_resource_usage', return_value=row(100)):
            self.assertIsNone(sampler.capture([p])['cpu_percent_one_core'])
        with patch.object(module, 'owned_resource_usage', return_value=None):
            missing = sampler.capture([p])
            self.assertIsNone(missing['phys_footprint_bytes'])
            self.assertIsNone(missing['cpu_delta_ns'])
        with patch.object(module, 'owned_resource_usage', return_value=row(200)):
            self.assertIsNone(sampler.capture([p])['cpu_delta_ns'])
        with patch.object(module, 'owned_resource_usage', return_value=row(300, start=4)):
            self.assertIsNone(sampler.capture([p])['cpu_delta_ns'])

    def test_owned_busy_child_has_measured_cpu_memory_and_cleanup(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache') as root:
            s = module.Supervisor(Path(root), deadline_seconds=3, interval_seconds=.05)
            code = 'import time; memory=bytearray(64*1024*1024); end=time.monotonic()+.7\nwhile time.monotonic()<end: pass'
            report = s.run([sys.executable, '-c', code])
            resources = report['resource_measurements']
            self.assertTrue(report['final_cleanup_observed_tree'], report)
            self.assertGreater(resources['observed_cpu_delta_ns'], 100_000_000)
            self.assertGreater(resources['peak_observed_tree_phys_footprint_bytes'], 50 * 1024**2)
            self.assertIn('owned_python', resources['observed_process_roles'])
            self.assertIsNone(resources['gpu_percent'])
            self.assertIsNone(report['footprint_bytes'])
            self.assertTrue(any(s['resource_usage']['cpu_percent_one_core'] is not None for s in report['samples']))


if __name__ == '__main__':
    unittest.main()

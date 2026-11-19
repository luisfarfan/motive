import ctypes
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / 'tools'))
from h19_memory_regions import ProcRegionInfo, inspect_owned_regions
spec = importlib.util.spec_from_file_location('h19_memory_supervisor', LAB / 'poc/browser-host/supervisor.py')
supervisor = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = supervisor
spec.loader.exec_module(supervisor)


class H19MemoryRegions(unittest.TestCase):
    def test_region_struct_matches_public_sdk(self):
        with tempfile.TemporaryDirectory(dir=LAB / '.cache') as directory:
            source, binary = Path(directory) / 'layout.c', Path(directory) / 'layout'
            source.write_text('#include <sys/proc_info.h>\n#include <stddef.h>\n#include <stdio.h>\n'
                'int main(void){printf("%zu %zu %zu", sizeof(struct proc_regioninfo),'
                'offsetof(struct proc_regioninfo,pri_address),offsetof(struct proc_regioninfo,pri_private_pages_resident));}\n')
            subprocess.run(['/usr/bin/xcrun', 'clang', str(source), '-o', str(binary)], check=True, capture_output=True)
            got = list(map(int, subprocess.check_output([str(binary)], text=True).split()))
            self.assertEqual(got, [ctypes.sizeof(ProcRegionInfo), ProcRegionInfo.address.offset, ProcRegionInfo.private_pages_resident.offset])

    def test_only_matching_identity_and_bounded_metadata(self):
        self.assertEqual(inspect_owned_regions(supervisor, (os.getpid(), (0,0)))['reason'], 'identity_mismatch')
        report = inspect_owned_regions(supervisor, (os.getpid(), supervisor.birth_identity(os.getpid())), max_regions=8)
        self.assertLessEqual(report['region_count'], 8)
        self.assertIsNone(report['unique_physical_bytes'])
        self.assertNotIn('paths', report)


if __name__ == '__main__':
    unittest.main()

from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from h22_memory_check import size,vm_summary

class MemorySummaryTests(unittest.TestCase):
    def test_units_do_not_confuse_virtual_gib_with_allocated_mib(self):
        self.assertEqual(size('30.8M'),round(30.8*1024**2))
        self.assertEqual(size('1.5G'),1610612736)
        self.assertEqual(size('0K'),0)
        for invalid in ('-1M','nan','inf','10MB','M',''):
            with self.assertRaises(ValueError):size(invalid)

    def test_incomplete_tables_cannot_be_reported_as_zero_usage(self):
        with self.assertRaisesRegex(ValueError,'VM_SUMMARY_TABLES'):vm_summary('Physical footprint: 40M\n')

    def test_real_retained_profile_keeps_distinct_categories(self):
        root=Path(__file__).resolve().parents[1]/'evidence/H22-cold1-memory600-r1'
        import json
        profile=json.loads((root/'memory-profile.json').read_text())
        process=next(x for x in profile['stages'][0]['processes'] if x['role']=='browser_host')
        report=vm_summary((root/process['path']).read_text())
        self.assertEqual(report['malloc_zones']['TOTAL']['allocated_bytes'],size('30.8M'))
        self.assertEqual(report['physical_footprint_rounded_bytes'],size('62.6M'))
        self.assertGreater(report['regions']['TOTAL']['virtual_bytes'],report['physical_footprint_rounded_bytes'])

if __name__=='__main__':unittest.main()

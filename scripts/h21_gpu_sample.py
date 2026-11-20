"""Read optional device-wide GPU telemetry exposed by this Mac's IORegistry.

These values include every app, are not Motive attribution, and carry no
utilization interval guarantee. No root, powermetrics or preference changes.
"""
import plistlib
import subprocess
import time


def sample_gpu():
    before = time.monotonic()
    result = {'scope':'device-wide, all applications', 'available':False,
              'interval_semantics':'driver-reported, not specified by this probe'}
    try:
        nodes = plistlib.loads(subprocess.check_output(
            ['/usr/sbin/ioreg','-a','-r','-c','IOAccelerator'], timeout=3))
        rows = []
        def visit(node):
            if isinstance(node,list):
                for v in node: visit(v)
            elif isinstance(node,dict):
                stats = node.get('PerformanceStatistics')
                if isinstance(stats,dict):
                    allowed = ('Device Utilization %','Renderer Utilization %','Tiler Utilization %',
                               'In use system memory','Alloc system memory','recoveryCount')
                    rows.append({'registry_name':node.get('IORegistryEntryName'),
                                 'statistics':{k:stats[k] for k in allowed if k in stats}})
                visit(node.get('IORegistryEntryChildren',[]))
        visit(nodes)
        result.update(available=bool(rows), devices=rows)
    except Exception as error: result['error'] = repr(error)
    result['host_bracket_s'] = [before,time.monotonic()]
    return result

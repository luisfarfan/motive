#!/usr/bin/env python3
"""Same 100-request bounded idle RPC observation used for H15 B1/B2 comparison."""
import json
import argparse
from pathlib import Path
import statistics
import time
from h7_support import Client, EVIDENCE

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path,
                    default=EVIDENCE / f'h15-control-latency-{time.time_ns()}.json')
args = parser.parse_args()
assert not args.output.exists(), 'Never replace historical latency evidence'
client = Client()
rows = []
try:
    pid = client.state()['pid']
    for _ in range(100):
        before = time.perf_counter()
        value = client.call('memory_diagnostics')['memory']
        elapsed = (time.perf_counter()-before)*1000
        assert value['pid'] == pid and value['status'] == 'PASS'
        rows.append({'rpc_ms':elapsed,'native_collection_us':value['collection_us']})
        time.sleep(.05)
finally:
    client.close()
values = sorted(r['rpc_ms'] for r in rows)
report = {'pid':pid,'samples':rows,'median_ms':statistics.median(values),
          'p95_ms':values[94],'maximum_ms':values[-1],'budget_p95_ms':20}
report['status'] = 'PASS' if report['p95_ms'] <= 20 else 'FAIL'
with args.output.open('x') as output:
    json.dump(report, output, indent=2)
print(json.dumps({k:v for k,v in report.items() if k!='samples'}))

#!/usr/bin/env python3
"""Same 100-request bounded idle RPC observation used for H15 B1/B2 comparison."""
import json
import statistics
import time
from h7_support import Client, EVIDENCE

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
(EVIDENCE/'h15-control-latency-b4.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='samples'}))

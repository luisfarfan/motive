"""Bounded vmmap summaries of supervisor-attributed CEF processes only.

Diagnostic runs are deliberately separate from unperturbed cadence/capacity.
No heap content, task memory dump, credential API or global instrumentation.
"""
import hashlib
import json
import subprocess
import threading
import time
from h19_memory_regions import inspect_owned_regions


class MemoryProbe:
    def __init__(self, output, supervisor_module):
        self.output = output
        self.supervisor = supervisor_module
        self.thread = None
        self.stages = []
        self.schedule = [60_000, 300_000, 570_000]
        self.errors = 0

    def sample(self, sample):
        if not self.schedule or sample['phase'] != 'running' or sample['elapsed_ms'] < self.schedule[0]:
            return
        if self.thread and self.thread.is_alive():
            return
        at = self.schedule.pop(0)
        processes = list(sample['resource_usage']['processes'])[:12]
        stage = {'requested_elapsed_ms': at, 'sample_elapsed_ms': sample['elapsed_ms'], 'processes': []}
        self.stages.append(stage)
        self.thread = threading.Thread(target=self.capture, args=(stage, processes), daemon=False)
        self.thread.start()

    def capture(self, stage, processes):
        deadline = time.monotonic() + 25
        for process in processes:
            row = {k: process[k] for k in ('pid','birth','role','proc_start_abstime')}
            stage['processes'].append(row)
            row['public_region_metadata'] = inspect_owned_regions(self.supervisor,
                (process['pid'],process['birth']),max_seconds=.05,max_regions=8192)
            if self.errors >= 2:
                row.update(status='NOT_EVALUATED', reason='two_failed_probes_stop_no_permission_bypass')
                continue
            if self.supervisor.birth_identity(process['pid']) != tuple(process['birth']):
                row.update(status='NOT_EVALUATED', reason='process_identity_changed')
                continue
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                row.update(status='NOT_EVALUATED', reason='stage_deadline')
                continue
            start = time.monotonic_ns()
            try:
                completed = subprocess.run(['/usr/bin/vmmap','-summary',str(process['pid'])], capture_output=True,
                    timeout=min(4,remaining), env={'PATH':'/usr/bin:/bin','LANG':'C'}, close_fds=True)
                data = completed.stdout + completed.stderr
                row['returncode'] = completed.returncode
                if len(data)>1024*1024:
                    row.update(status='FAIL',reason='bounded_summary_size');self.errors+=1;continue
                relative = 'vmmap-%d-%d.txt' % (stage['requested_elapsed_ms'],process['pid'])
                with (self.output/relative).open('xb') as stream:stream.write(data)
                row.update(path=relative,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),
                    identity_still_matched=self.supervisor.birth_identity(process['pid'])==tuple(process['birth']))
                row['status'] = 'PASS' if completed.returncode==0 and row['identity_still_matched'] else 'FAIL'
                if row['status']=='FAIL':self.errors+=1
            except subprocess.TimeoutExpired:
                row.update(status='FAIL',reason='vmmap_deadline');self.errors+=1
            finally:
                row['probe_ms']=(time.monotonic_ns()-start)/1e6

    def finish(self):
        if self.thread:self.thread.join(timeout=30)
        if self.thread and self.thread.is_alive():raise ValueError('MEMORY_PROBE_NOT_JOINED')
        report={'scope':'metadata-only diagnostic; vmmap can perturb/pause target, not performance acceptance',
                'stages':self.stages,'unreached_stages_ms':self.schedule,
                'keychain_accessed':False,'memory_contents_captured':False}
        with (self.output/'memory-profile.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')

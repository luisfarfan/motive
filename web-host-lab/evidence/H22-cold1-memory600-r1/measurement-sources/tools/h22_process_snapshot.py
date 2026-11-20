"""Public libproc metadata observer. No task ports, process arguments or memory reads.

H22 only: the legacy H19 observer still uses ps. CPU continues to be measured by
the independent rusage sampler; this observer does not invent a ps CPU value.
"""
import ctypes
import os
import time


class NativeSnapshot:
    def __init__(self, supervisor):
        self.m = supervisor
        self.lib = supervisor._LIBPROC
        self.lib.proc_listallpids.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.proc_listallpids.restype = ctypes.c_int
        self.calls = 0
        self.max_ns = 0

    def __call__(self):
        start = time.monotonic_ns()
        pids = (ctypes.c_int * 65536)()
        count = self.lib.proc_listallpids(pids, ctypes.sizeof(pids))
        if count <= 0 or count >= len(pids):
            raise RuntimeError('PROCESS_LIST_UNAVAILABLE_OR_TRUNCATED')
        result = {}
        for pid in pids[:count]:
            if pid <= 0:
                continue
            info = self.m.BsdInfo()
            if self.lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info)) != ctypes.sizeof(info):
                continue  # exited or inaccessible; never attribute unknown identities
            if info.prefix[3] != pid or info.prefix[5] != os.getuid():
                continue
            birth = (info.start_seconds, info.start_microseconds)
            task = self.m.ProcTaskInfo()
            available = self.lib.proc_pidinfo(pid, 4, 0, ctypes.byref(task), ctypes.sizeof(task)) == ctypes.sizeof(task)
            if self.m.birth_identity(pid) != birth:
                continue
            result[pid] = self.m.Process(pid, info.prefix[4], info.counts[1],
                (task.resident_size + 1023) // 1024 if available else -1,
                None, birth, 'Z' if info.prefix[1] == 5 else '?')
        self.calls += 1
        self.max_ns = max(self.max_ns, time.monotonic_ns() - start)
        return result

    def report(self):
        return {'api': 'proc_listallpids + PROC_PIDTBSDINFO + PROC_PIDTASKINFO',
                'calls': self.calls, 'max_duration_ms': self.max_ns / 1e6,
                'cpu_percent_ps': None, 'capacity': 65536,
                'scope': 'same-user process metadata; observed tree only, not hostile confinement'}

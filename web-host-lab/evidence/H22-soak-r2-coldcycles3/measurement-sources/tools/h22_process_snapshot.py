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
        self.system = supervisor._LIBSYSTEM
        for name in ('mach_absolute_time','mach_continuous_time'):
            getattr(self.system,name).argtypes=[]
            getattr(self.system,name).restype=ctypes.c_uint64
        self.initial_lower,self.initial_upper=self.clock_offset()
        self.suspend_lower_bound_ns=0
        self.clock_uncertainty_ns=0

    def clock_offset(self):
        before=self.system.mach_absolute_time()
        continuous=self.system.mach_continuous_time()
        after=self.system.mach_absolute_time()
        return self.m.mach_ticks_to_ns(continuous-after),self.m.mach_ticks_to_ns(continuous-before)

    def __call__(self):
        start = time.monotonic_ns()
        lower,upper=self.clock_offset()
        self.clock_uncertainty_ns=max(self.clock_uncertainty_ns,upper-lower)
        self.suspend_lower_bound_ns=max(self.suspend_lower_bound_ns,lower-self.initial_upper)
        if self.suspend_lower_bound_ns>50_000_000:
            raise RuntimeError('SYSTEM_SUSPEND_INTERRUPTION')
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
                'suspend_elapsed_lower_bound_ms':self.suspend_lower_bound_ns/1e6,
                'paired_clock_max_uncertainty_ms':self.clock_uncertainty_ns/1e6,
                'suspend_clock_api':'mach_continuous_time minus bracketed mach_absolute_time',
                'cpu_percent_ps': None, 'capacity': 65536,
                'scope': 'same-user process metadata; observed tree only, not hostile confinement'}

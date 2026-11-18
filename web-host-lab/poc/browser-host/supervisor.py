"""External supervisor for one explicitly launched tree. Does not launch CEF itself.

Process-group containment is not an OS sandbox. A hostile process can escape before
observation; third-party content stays blocked. Tests launch owned Python fixtures.
"""
from collections import deque
from dataclasses import dataclass
import os
import ctypes
import json
from pathlib import Path
import signal
import subprocess
import time
import uuid


@dataclass(frozen=True)
class Process:
    pid: int
    parent: int
    group: int
    rss_kib: int
    cpu_percent: float
    birth: tuple[int, int]
    state: str

    @property
    def identity(self):
        return self.pid, self.birth


class BsdInfo(ctypes.Structure):
    # Public macOS SDK sys/proc_info.h, struct proc_bsdinfo. Names are read into
    # fixed native storage but never returned or logged; only identity is used.
    _fields_ = [('prefix', ctypes.c_uint32 * 12), ('comm', ctypes.c_char * 16),
                ('name', ctypes.c_char * 32), ('counts', ctypes.c_uint32 * 6),
                ('start_seconds', ctypes.c_uint64), ('start_microseconds', ctypes.c_uint64)]


_LIBPROC = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
_LIBPROC.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
_LIBPROC.proc_pidinfo.restype = ctypes.c_int
_LIBPROC.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
_LIBPROC.proc_pid_rusage.restype = ctypes.c_int
_LIBPROC.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
_LIBPROC.proc_pidpath.restype = ctypes.c_int


class RusageInfoV0(ctypes.Structure):
    # Public SDK sys/resource.h: RUSAGE_INFO_V0. CPU fields use Mach ticks;
    # normalize through the public timebase, never assume ticks == nanoseconds.
    _fields_ = [('uuid', ctypes.c_uint8 * 16)] + [(name, ctypes.c_uint64) for name in (
        'user_time', 'system_time', 'pkg_idle_wkups', 'interrupt_wkups', 'pageins',
        'wired_size', 'resident_size', 'phys_footprint', 'proc_start_abstime', 'proc_exit_abstime')]


class MachTimebaseInfo(ctypes.Structure):
    _fields_ = [('numer', ctypes.c_uint32), ('denom', ctypes.c_uint32)]


_LIBSYSTEM = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
_LIBSYSTEM.mach_timebase_info.argtypes = [ctypes.POINTER(MachTimebaseInfo)]
_LIBSYSTEM.mach_timebase_info.restype = ctypes.c_int
_TIMEBASE = MachTimebaseInfo()
if _LIBSYSTEM.mach_timebase_info(ctypes.byref(_TIMEBASE)) != 0 or not _TIMEBASE.denom:
    raise RuntimeError('MACH_TIMEBASE_UNAVAILABLE')


def mach_ticks_to_ns(ticks):
    return ticks * _TIMEBASE.numer // _TIMEBASE.denom


def owned_resource_usage(process):
    """Read only a PID already attributed to this launch; reject identity races."""
    if birth_identity(process.pid) != process.birth:
        return None
    usage = RusageInfoV0()
    if _LIBPROC.proc_pid_rusage(process.pid, 0, ctypes.byref(usage)) != 0:
        return None
    path = ctypes.create_string_buffer(4096)  # Public PROC_PIDPATHINFO_MAXSIZE.
    count = _LIBPROC.proc_pidpath(process.pid, path, len(path))
    name = os.path.basename(os.fsdecode(path.value)) if count > 0 else ''
    roles = {'MotiveBrowserFixture': 'browser_host', 'MotiveBrowserFixture Helper': 'helper_unspecified'}
    roles.update({'MotiveBrowserFixture Helper (' + role + ')': role.lower() + '_helper'
                  for role in ('Alerts', 'GPU', 'Plugin', 'Renderer')})
    role = roles.get(name, 'owned_python' if name.lower().startswith('python') else 'other_owned_process')
    if birth_identity(process.pid) != process.birth:
        return None
    return {'pid': process.pid, 'birth': list(process.birth), 'role': role,
            'proc_start_abstime': usage.proc_start_abstime,
            'user_time_mach_ticks': usage.user_time, 'system_time_mach_ticks': usage.system_time,
            'user_time_ns': mach_ticks_to_ns(usage.user_time), 'system_time_ns': mach_ticks_to_ns(usage.system_time),
            'cpu_time_ns': mach_ticks_to_ns(usage.user_time + usage.system_time),
            'resident_bytes': usage.resident_size, 'phys_footprint_bytes': usage.phys_footprint}


class ResourceSampler:
    """Consecutive samples only; exited/new/missed processes never become zero CPU."""
    def __init__(self):
        self.previous = {}
        self.previous_ns = None
        self.total_samples = 0
        self.partial_samples = 0
        self.peak_footprint = None
        self.cpu_intervals = 0
        self.cpu_delta_ns = 0
        self.wall_delta_ns = 0
        self.observed_roles = {}

    def capture(self, processes):
        started = time.monotonic_ns()
        wall = None if self.previous_ns is None else started - self.previous_ns
        current, records = {}, []
        for process in processes:
            row = owned_resource_usage(process)
            if row is None:
                continue
            current[process.identity] = row
            self.observed_roles[process.identity] = row['role']
            old = self.previous.get(process.identity)
            delta = None
            if old and wall and old['proc_start_abstime'] == row['proc_start_abstime']:
                difference = row['cpu_time_ns'] - old['cpu_time_ns']
                if difference >= 0:
                    delta = difference
            row['cpu_delta_ns'] = delta
            records.append(row)
        deltas = [r['cpu_delta_ns'] for r in records if r['cpu_delta_ns'] is not None]
        footprint = sum(r['phys_footprint_bytes'] for r in records)
        memory_complete = bool(processes) and len(records) == len(processes)
        # Even complete coverage of observed identities cannot discover children
        # that were born and exited entirely between two process snapshots.
        cpu_complete = (memory_complete and len(deltas) == len(processes)
                        and set(current) == set(self.previous))
        percent = 100 * sum(deltas) / wall if deltas and wall else None
        if memory_complete:
            self.peak_footprint = max(self.peak_footprint or 0, footprint)
        if deltas and wall:
            self.cpu_intervals += 1
            self.cpu_delta_ns += sum(deltas)
            self.wall_delta_ns += wall
        self.total_samples += 1
        if not (memory_complete and cpu_complete):
            self.partial_samples += 1
        self.previous, self.previous_ns = current, started
        return {'version': 1, 'sample_monotonic_ns': started,
                'sample_duration_ns': time.monotonic_ns() - started, 'wall_delta_ns': wall,
                'attempted_processes': len(processes), 'sampled_processes': len(records),
                'cpu_delta_processes': len(deltas), 'cpu_observed_identity_coverage_complete': cpu_complete,
                'cpu_percent_one_core': percent, 'cpu_delta_ns': sum(deltas) if deltas else None,
                'phys_footprint_bytes': footprint if memory_complete else None,
                'observed_phys_footprint_bytes': footprint if records else None,
                'memory_observed_identity_coverage_complete': memory_complete,
                'processes': records, 'gpu_percent': None}

    def report(self):
        counts = {}
        for role in self.observed_roles.values():
            counts[role] = counts.get(role, 0) + 1
        return {'version': 1, 'api': 'proc_pid_rusage(RUSAGE_INFO_V0)',
                'mach_timebase': {'numer': _TIMEBASE.numer, 'denom': _TIMEBASE.denom},
                'cpu_unit': 'nanoseconds; percent 100 equals one fully occupied core',
                'total_samples': self.total_samples, 'partial_samples': self.partial_samples,
                'valid_cpu_intervals': self.cpu_intervals, 'observed_cpu_delta_ns': self.cpu_delta_ns,
                'measured_wall_delta_ns': self.wall_delta_ns,
                'observed_cpu_mean_percent_one_core': (100 * self.cpu_delta_ns / self.wall_delta_ns
                                                     if self.wall_delta_ns else None),
                'peak_observed_tree_phys_footprint_bytes': self.peak_footprint,
                'observed_process_roles': counts, 'gpu_percent': None,
                'limits': ['Only consecutive observations of matching PID/birth/start identity contribute CPU deltas.',
                           'CPU before first/after last observation and processes shorter than the sampling interval may be missed.',
                           'Memory is a sequential sum of per-process physical footprints, not a coalition or unique physical-page total.',
                           'Reported CPU excludes the supervisor and process-list collection overhead.',
                           'Roles identify observed executable basenames; a helper role does not measure GPU utilization.',
                           'Historical cpu_percent_ps remains ps output; legacy footprint_bytes remains unspecified/null.']}


def birth_identity(pid):
    info = BsdInfo()
    if _LIBPROC.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info)) != ctypes.sizeof(info):
        return None
    if info.prefix[3] != pid or info.prefix[5] != os.getuid():
        return None
    return info.start_seconds, info.start_microseconds


def snapshot():
    # No command lines, environment, device IDs or arbitrary diagnostic strings.
    text = subprocess.check_output(['/bin/ps', '-axo', 'pid=,ppid=,pgid=,rss=,%cpu=,stat='], text=True, timeout=1)
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 6:
            raise RuntimeError('PROCESS_SNAPSHOT_FORMAT')
        pid = int(fields[0])
        identity = birth_identity(pid)
        if identity is None:
            continue
        p = Process(pid, int(fields[1]), int(fields[2]), int(fields[3]), float(fields[4]), identity, fields[5])
        result[p.pid] = p
    return result


class Supervisor:
    def __init__(self, root: Path, *, deadline_seconds=5.0, rss_limit_kib=2 * 1024 * 1024, interval_seconds=0.025):
        if not 0.05 <= deadline_seconds <= 720 or not 1 <= rss_limit_kib <= 16 * 1024 * 1024 or not 0.005 <= interval_seconds <= 1:
            raise ValueError('SUPERVISOR_LIMITS')
        self.root = Path(root).resolve(strict=True)
        st = self.root.stat()
        if st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise ValueError('PRIVATE_ROOT_REQUIRED')
        self.deadline_seconds = deadline_seconds
        self.rss_limit_kib = rss_limit_kib
        self.interval_seconds = interval_seconds
        self.session_id = uuid.uuid4().hex
        self.generation = 0
        self.active = False
        self.last_report = None

    def run(self, executable_and_args, *, cancelled=lambda: False, on_sample=None):
        """Trusted launch API, never exposed to package/MCP/renderer input.

        The caller must independently hold the repository-specific authorization
        for any browser launch. This module/test runner grants no such approval.
        """
        if self.active:
            raise ValueError('SUPERVISOR_BUSY')
        if not executable_and_args or not Path(executable_and_args[0]).is_absolute():
            raise ValueError('ABSOLUTE_EXECUTABLE_REQUIRED')
        self.active = True
        self.generation += 1
        run_root = self.root / f'{self.session_id}-generation-{self.generation}'
        samples = deque(maxlen=256)
        resources = ResourceSampler()
        known = {}
        start = time.monotonic()
        reason = 'exit'
        peak_rss = 0
        child = None
        report = None
        try:
            run_root.mkdir(mode=0o700)
            # Files are private and bounded by the supervised, controlled fixture;
            # no stdout pipe can deadlock the supervisor. CEF logging is disabled.
            with (run_root / 'stdout.log').open('xb') as out, (run_root / 'stderr.log').open('xb') as err:
                os.chmod(out.name, 0o600); os.chmod(err.name, 0o600)
                child = subprocess.Popen(list(executable_and_args), cwd=run_root, stdin=subprocess.DEVNULL, stdout=out, stderr=err, close_fds=True, start_new_session=True,
                    env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'TMPDIR': str(run_root), 'LANG': 'C'})
                group = child.pid

                leader_identity = birth_identity(child.pid)
                if leader_identity is not None:
                    # Own session leader, checked before any group fallback signal.
                    known[(child.pid, leader_identity)] = Process(child.pid, os.getpid(), group, 0, 0, leader_identity, '')

                def observe():
                    current = snapshot()
                    # Group members belong to the launch session; extend to
                    # descendants while their parent identity is still observed.
                    members = {p.pid: p for p in current.values() if p.group == group}
                    changed = True
                    while changed:
                        changed = False
                        for p in current.values():
                            parent = current.get(p.parent)
                            if p.pid not in members and parent and parent.identity in known:
                                members[p.pid] = p; changed = True
                        for p in members.values():
                            known[p.identity] = p
                    for identity, previous in list(known.items()):
                        p = current.get(previous.pid)
                        if p and p.identity == identity:
                            members[p.pid] = p
                    return current, members

                while True:
                    current, members = observe()
                    live = [p for p in members.values() if not p.state.startswith('Z')]
                    rss = sum(p.rss_kib for p in live)
                    peak_rss = max(peak_rss, rss)
                    sample = {'elapsed_ms': round((time.monotonic() - start) * 1000, 3), 'processes': len(live),
                              'rss_kib': rss, 'cpu_percent_ps': sum(p.cpu_percent for p in live),
                              'resource_usage': resources.capture(live)}
                    samples.append(sample)
                    if on_sample is not None:
                        on_sample(sample)
                    if child.poll() is not None:
                        break
                    if cancelled(): reason = 'cancelled'; break
                    if rss > self.rss_limit_kib: reason = 'rss_limit'; break
                    if time.monotonic() - start >= self.deadline_seconds: reason = 'deadline'; break
                    time.sleep(self.interval_seconds)

                cleanup_start = time.monotonic()
                # TERM then KILL only processes whose observed PID/birth still
                # matches this launched tree; never kill by name or unknown PID.
                for sig, seconds in [(signal.SIGTERM, 0.5), (signal.SIGKILL, 1.0)]:
                    current, members = observe()
                    alive = [p for p in members.values() if not p.state.startswith('Z')]
                    if not alive:
                        break
                    for p in alive:
                        latest = snapshot().get(p.pid)
                        if latest and latest.identity == p.identity:
                            try: os.kill(p.pid, sig)
                            except ProcessLookupError: pass
                    until = time.monotonic() + seconds
                    while time.monotonic() < until:
                        child.poll()
                        _, members = observe()
                        if not any(not p.state.startswith('Z') for p in members.values()): break
                        time.sleep(self.interval_seconds)
                try: returncode = child.wait(timeout=0.1)
                except subprocess.TimeoutExpired: returncode = None
                _, remaining = observe()
                remaining_live = [p.pid for p in remaining.values() if not p.state.startswith('Z')]
                report = {'session_id': self.session_id, 'generation': self.generation, 'reason': reason, 'returncode': returncode, 'elapsed_ms': round((time.monotonic() - start) * 1000, 3),
                    'shutdown_ms': round((time.monotonic() - cleanup_start) * 1000, 3), 'observed_processes': len(known), 'remaining_observed_live_pids': remaining_live,
                    'cleanup_observed_tree': not remaining_live and returncode is not None, 'peak_tree_rss_kib': peak_rss, 'samples': list(samples),
                    'footprint_bytes': None, 'gpu_percent': None, 'launch_kind': 'trusted_caller_supplied_executable',
                    'scope': 'observed owned tree; not proof against unobserved process escape or an OS sandbox'}
                report['resource_measurements'] = resources.report()
                report['sample_retention'] = {'capacity': samples.maxlen, 'retained': len(samples),
                                              'dropped_oldest': max(0, resources.total_samples - len(samples))}
                return report
        except BaseException as error:
            report = {'session_id': self.session_id, 'generation': self.generation,
                      'reason': 'supervisor_error', 'error_type': type(error).__name__,
                      'scope': 'best-effort cleanup of observed owned tree'}
            report.update(samples=list(samples), resource_measurements=resources.report())
            raise
        finally:
            # This path does not use snapshot(): it also runs after ps failure or
            # a failing cancellation callback, including an already-exited root.
            # A previously observed child may have escaped its original group.
            if child is not None and child.poll() is None:
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            for identity, previous in known.items():
                if birth_identity(previous.pid) == identity[1]:
                    try: os.kill(previous.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
            if child is not None:
                try: child.wait(timeout=2)
                except subprocess.TimeoutExpired: pass
            def still_alive(identity):
                info = BsdInfo()
                count = _LIBPROC.proc_pidinfo(identity[0], 3, 0, ctypes.byref(info), ctypes.sizeof(info))
                return (count == ctypes.sizeof(info) and info.prefix[3] == identity[0]
                        and info.prefix[5] == os.getuid() and info.prefix[1] != 5
                        and (info.start_seconds, info.start_microseconds) == identity[1])
            until = time.monotonic() + 1
            remaining = [identity[0] for identity in known if birth_identity(identity[0]) == identity[1]]
            while remaining and time.monotonic() < until:
                time.sleep(self.interval_seconds)
                remaining = [identity[0] for identity in known if birth_identity(identity[0]) == identity[1]]
            if report is not None:
                report['final_remaining_observed_pids'] = remaining
                report['final_remaining_observed_live_pids'] = [identity[0] for identity in known if still_alive(identity)]
                report['final_cleanup_observed_tree'] = not remaining and (child is None or child.poll() is not None)
                self.last_report = report
                try:
                    with (run_root / 'supervisor.json').open('x') as output:
                        os.chmod(output.name, 0o600)
                        json.dump(report, output, indent=2)
                        output.write('\n')
                except OSError:
                    # Preserve the original exception and in-memory report.
                    report['report_write_failed'] = True
            self.active = False

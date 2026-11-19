"""Bounded metadata-only public macOS region accounting for supervised own PIDs.

Caller supplies identities freshly attributed by Supervisor; never accept a PID
from a widget or user-provided package. No task ports, paths or memory bytes read.
"""
import ctypes
import os
import time


class ProcRegionInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in ('protection', 'max_protection', 'inheritance', 'flags')]
    _fields_ += [('offset', ctypes.c_uint64)]
    _fields_ += [(name, ctypes.c_uint32) for name in ('behavior', 'user_wired_count', 'user_tag',
        'pages_resident', 'pages_shared_now_private', 'pages_swapped_out', 'pages_dirtied', 'ref_count',
        'shadow_depth', 'share_mode', 'private_pages_resident', 'shared_pages_resident', 'obj_id', 'depth')]
    _fields_ += [('address', ctypes.c_uint64), ('size', ctypes.c_uint64)]


def inspect_owned_regions(supervisor_module, identity, *, max_seconds=.05, max_regions=8192):
    pid, birth = identity
    if supervisor_module.birth_identity(pid) != tuple(birth):
        return {'status': 'NOT_EVALUATED', 'reason': 'identity_mismatch'}
    started = time.monotonic_ns()
    address, count, totals, modes = 0, 0, {}, {}
    fields = ('pages_resident', 'pages_shared_now_private', 'pages_swapped_out', 'pages_dirtied',
              'private_pages_resident', 'shared_pages_resident')
    reason, error = 'region_limit', None
    while count < max_regions:
        if time.monotonic_ns() - started >= max_seconds*1e9:
            reason = 'time_limit'
            break
        region = ProcRegionInfo()
        ctypes.set_errno(0)
        size = supervisor_module._LIBPROC.proc_pidinfo(pid, 7, address, ctypes.byref(region), ctypes.sizeof(region))
        if size != ctypes.sizeof(region):
            reason, error = 'api_end_or_failure', ctypes.get_errno()
            break
        if region.address < address or not region.size or region.address+region.size <= address:
            reason = 'nonmonotonic_map'
            break
        count += 1
        address = region.address + region.size
        totals['virtual_region_bytes'] = totals.get('virtual_region_bytes', 0) + region.size
        for field in fields:
            totals[field] = totals.get(field, 0) + getattr(region, field)
        mode = {1:'copy_on_write', 2:'private', 3:'empty', 4:'shared', 5:'true_shared',
                6:'private_aliased', 7:'shared_aliased', 8:'large_page'}.get(region.share_mode, 'other')
        modes[mode] = modes.get(mode, 0) + 1
    matched = supervisor_module.birth_identity(pid) == tuple(birth)
    if not matched:
        return {'status': 'NOT_EVALUATED', 'reason': 'identity_changed'}
    pagesize = os.sysconf('SC_PAGE_SIZE')
    return {'status': 'PARTIAL' if count else 'NOT_EVALUATED', 'pid': pid, 'birth': list(birth),
        'api': 'proc_pidinfo(PROC_PIDREGIONINFO)', 'region_count': count, 'walk_stop': reason, 'errno': error,
        'page_size_bytes': pagesize, 'elapsed_ms': (time.monotonic_ns()-started)/1e6,
        'totals': totals, 'page_bytes': {k.removesuffix('_pages') + '_bytes': v*pagesize for k,v in totals.items() if k != 'virtual_region_bytes'},
        'region_share_modes': modes, 'unique_physical_bytes': None,
        'limits': ['Sequential region metadata, not a simultaneous map or unique physical-page inventory.',
                   'Aliased/shared/COW pages may overlap; these categories must not be added as unique RAM.',
                   'Virtual regions are address-space reservations; dirty/resident/swapped values have distinct meanings.',
                   'No reclaimability or allocator live-byte inference follows from region residency.']}

"""Explicit, temporary CoreGraphics mode change for an authorized H21 test.

CGDirectDisplay.h documents CGDisplaySetDisplayMode as process-lifetime only.
The caller must still restore and verify the original mode before completing.
This module never captures pixels, selects a default display or writes defaults.
"""
import ctypes as C
import time


def equivalent_mode(left, right):
    # CoreGraphics may canonicalize duplicate I/O mode IDs during an app-only
    # change. Require every observed physical property and flag to agree.
    return {k:v for k,v in left.items() if k != 'mode_id'} == {k:v for k,v in right.items() if k != 'mode_id'}


class TemporaryDisplayMode:
    def __init__(self, uuid, width, height):
        self.cg = C.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        self.colorsync = C.CDLL('/System/Library/Frameworks/ColorSync.framework/ColorSync')
        self.cf = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        signatures = {
            'CGGetActiveDisplayList': ([C.c_uint32, C.POINTER(C.c_uint32), C.POINTER(C.c_uint32)], C.c_int),
            'CGDisplayCreateUUIDFromDisplayID': ([C.c_uint32], C.c_void_p),
            'CGDisplayCopyDisplayMode': ([C.c_uint32], C.c_void_p),
            'CGDisplayCopyAllDisplayModes': ([C.c_uint32, C.c_void_p], C.c_void_p),
            'CGDisplaySetDisplayMode': ([C.c_uint32, C.c_void_p, C.c_void_p], C.c_int),
            'CGDisplayIsInMirrorSet': ([C.c_uint32], C.c_uint32),
            'CGDisplayModeGetRefreshRate': ([C.c_void_p], C.c_double),
            'CGDisplayModeGetIODisplayModeID': ([C.c_void_p], C.c_uint32),
            'CGDisplayModeGetIOFlags': ([C.c_void_p], C.c_uint32),
            'CGDisplayModeIsUsableForDesktopGUI': ([C.c_void_p], C.c_bool),
        }
        for suffix in ('Width', 'Height', 'PixelWidth', 'PixelHeight'):
            signatures['CGDisplayModeGet'+suffix] = ([C.c_void_p], C.c_size_t)
        for name, (args, result) in signatures.items():
            library = self.colorsync if name == 'CGDisplayCreateUUIDFromDisplayID' else self.cg
            function = getattr(library, name); function.argtypes = args; function.restype = result
        signatures = {
            'CFUUIDCreateString': ([C.c_void_p, C.c_void_p], C.c_void_p),
            'CFStringGetCString': ([C.c_void_p, C.c_void_p, C.c_long, C.c_uint32], C.c_bool),
            'CFArrayGetCount': ([C.c_void_p], C.c_long),
            'CFArrayGetValueAtIndex': ([C.c_void_p, C.c_long], C.c_void_p),
            'CFRelease': ([C.c_void_p], None),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.cf, name); function.argtypes = args; function.restype = result
        displays = (C.c_uint32*32)(); count = C.c_uint32()
        assert self.cg.CGGetActiveDisplayList(32, displays, C.byref(count)) == 0
        matches = []
        for ident in displays[:count.value]:
            value = self.colorsync.CGDisplayCreateUUIDFromDisplayID(ident)
            text = self.cf.CFUUIDCreateString(None, value); buffer = C.create_string_buffer(128)
            try:
                assert self.cf.CFStringGetCString(text, buffer, len(buffer), 0x08000100)
                if buffer.value.decode() == uuid: matches.append(ident)
            finally:
                self.cf.CFRelease(text); self.cf.CFRelease(value)
        assert len(matches) == 1, 'Explicit authorized display unavailable'
        self.display = matches[0]
        assert not self.cg.CGDisplayIsInMirrorSet(self.display), 'Mirrored displays are outside this test'
        self.original = self.cg.CGDisplayCopyDisplayMode(self.display)
        self.modes = self.cg.CGDisplayCopyAllDisplayModes(self.display, None)
        self.before = self.info(self.original)
        assert (self.before['width'], self.before['height']) == (3840,1080), 'Authorized initial geometry changed'
        candidates = [self.cf.CFArrayGetValueAtIndex(self.modes, i)
                      for i in range(self.cf.CFArrayGetCount(self.modes))]
        candidates = [m for m in candidates if self.info(m)['width'] == width and self.info(m)['height'] == height
                      and self.info(m)['refresh_hz'] == self.before['refresh_hz']
                      and self.cg.CGDisplayModeIsUsableForDesktopGUI(m)]
        assert candidates, 'Authorized temporary mode unavailable'
        self.target = min(candidates, key=lambda m: self.info(m)['mode_id'])
        self.requested = self.info(self.target); self.changed = False

    def info(self, mode):
        assert mode, 'Display mode unavailable'
        return {key: getattr(self.cg, 'CGDisplayModeGet'+suffix)(mode) for key, suffix in
                [('width','Width'), ('height','Height'), ('pixel_width','PixelWidth'),
                 ('pixel_height','PixelHeight'), ('refresh_hz','RefreshRate'), ('mode_id','IODisplayModeID'),
                 ('io_flags','IOFlags')]}

    def current(self):
        mode = self.cg.CGDisplayCopyDisplayMode(self.display)
        try: return self.info(mode)
        finally:
            if mode: self.cf.CFRelease(mode)

    def set_mode(self, mode, expected):
        code = self.cg.CGDisplaySetDisplayMode(self.display, mode, None)
        assert code == 0, 'CoreGraphics mode change rejected: '+str(code)
        deadline = time.monotonic()+5
        while True:
            observed = self.current()
            if equivalent_mode(observed, expected): return observed
            assert time.monotonic()<deadline, 'Requested mode not observed: '+str(observed)
            time.sleep(.1)

    def apply(self):
        assert self.current() == self.before, 'Display changed before test'
        self.changed = True
        return self.set_mode(self.target, self.requested)

    def restore(self):
        if self.changed:
            observed = self.current()
            assert any(equivalent_mode(observed, mode) for mode in (self.requested, self.before)), 'Unowned display mode change; restoration withheld'
            self.set_mode(self.original, self.before)
            self.changed = False
        assert equivalent_mode(self.current(), self.before), 'Original mode not restored'
        return self.current()

    def close(self):
        try: self.restore()
        finally:
            self.cf.CFRelease(self.modes); self.cf.CFRelease(self.original)

"""Exclusive local cache staging; never follow a destination or .part symlink."""
import os
import pathlib
import stat
import tempfile


def regular_cache_file(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('Cache destination is not a regular file')
    return True


def write_cache_atomically(path, writer, validate=None):
    """Create a new cache entry; writer receives an exclusively opened stream."""
    if regular_cache_file(path):
        raise ValueError('Cache destination already exists')
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.download-', dir=path.parent)
    temporary = pathlib.Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            writer(stream)
        if validate:
            validate(temporary)
        # Reject a destination introduced while staging, including dangling
        # symlinks. replace itself never follows a destination symlink.
        if regular_cache_file(path):
            raise ValueError('Cache destination appeared during staging')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

"""Read only the console lock Boolean; never return session/user metadata."""
import re
import subprocess


def parse_console_locked(text):
    matches = re.findall(r'^\s*"IOConsoleLocked"\s*=\s*(Yes|No)\s*$', text, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError('Console lock state unavailable or ambiguous')
    return matches[0] == 'Yes'


def console_locked():
    raw = subprocess.check_output(['/usr/sbin/ioreg', '-n', 'Root', '-d1', '-l'],text=True,timeout=5)
    return parse_console_locked(raw)

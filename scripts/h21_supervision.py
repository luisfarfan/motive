"""Last-resort termination of a fresh, unreaped supervisor-owned child only."""


def terminate_owned_child(child, reason, binary_sha256):
    # Popen keeps ownership until wait/reap. Never accept a PID from a file,
    # socket, process scan, application bundle lookup or user session.
    if child.poll() is not None:
        return None
    child.kill()
    code = child.wait(timeout=10)
    return {'pid':child.pid, 'reason':reason, 'binary_sha256':binary_sha256,
            'exit_code':code, 'normal_shutdown':False}

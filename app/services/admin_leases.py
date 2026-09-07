"""Kernel liveness for a shared local runtime, independent of hostname/PID reuse.

Each durable claim has a unique lock inode. Hold its descriptor until work stops;
video children inherit it. Never unlink these files or expire a live lock by time.
"""
import fcntl
import hashlib
import json
import os
import stat
from datetime import timezone

from sqlalchemy import event


def lock_path(engine, lease):
    settings = getattr(engine, '_admin_settings', None)
    if settings is None:
        return None
    identity = [lease.kind, lease.job_id, lease.hostname, lease.pid,
                lease.created_at.replace(tzinfo=timezone.utc).isoformat(timespec='microseconds')]
    name = hashlib.sha256(json.dumps(identity).encode()).hexdigest() + '.lock'
    return settings.runtime_root / 'tmp' / 'lease-locks' / name


def _guards(engine):
    if not hasattr(engine, '_admin_lease_guards'):
        engine._admin_lease_guards = {}
    return engine._admin_lease_guards


def acquire_guard(session, lease):
    engine = session.get_bind()
    path = lock_path(engine, lease)
    if path is None:
        raise RuntimeError('Shared runtime is required for worker claims')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RuntimeError('Lease lock must be a regular file')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    key = (lease.kind, lease.job_id)
    guard = (path, fd)
    _guards(engine)[key] = guard
    if 'admin_pending_guards' not in session.info:
        pending = session.info['admin_pending_guards'] = {}

        def committed(_session):
            pending.clear()

        def transaction_ended(_session, transaction):
            if transaction.parent is None:
                # Includes Session.close after an exception before commit. A
                # rolled-back claim must not retain a kernel lock in this process.
                for pending_key, pending_guard in pending.items():
                    if _guards(engine).get(pending_key) == pending_guard:
                        _guards(engine).pop(pending_key)
                    os.close(pending_guard[1])
                pending.clear()

        event.listen(session, 'after_commit', committed)
        event.listen(session, 'after_transaction_end', transaction_ended)
    session.info['admin_pending_guards'][key] = guard


def guard_fd(engine, kind, job_id):
    guard = _guards(engine).get((kind, job_id))
    return guard[1] if guard else None


def take_guard(engine, kind, job_id):
    return _guards(engine).pop((kind, job_id), None)


def guard_alive(engine, lease):
    """True=locked, False=proven unlocked, None=legacy/unknown provenance."""
    path = lock_path(engine, lease)
    if path is None:
        return None
    try:
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError:
        return True  # Inaccessible evidence cannot justify recovery.
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return True
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except OSError:
            return True
    finally:
        os.close(fd)

"""Real local process/lock ownership survives hostnames and PID reuse."""
import json
import os
import socket
import subprocess
import sys

import pytest
from sqlmodel import Session, select

from app.admin_models import AdminLease
from app.analyst_models import AnalystJob
from app.models import Analysis
from app.services.admin_scheduling import claim_video, recover_dead_leases, release_lease
from tests.test_admin_auth import admin_app
from tests.test_admin_recovery import seed_job


def recover(app):
    with Session(app.state.engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        recover_dead_leases(session)
        session.commit()


@pytest.mark.parametrize('old_hostname', ['old-container', socket.gethostname()])
def test_kernel_owner_lock_recovers_dead_container_even_with_reused_live_pid(admin_app, old_hostname):
    app, _ = admin_app
    row = seed_job(app, 'report', attempts=1)
    # The child deliberately records this still-live parent PID. Only the kernel
    # lock can distinguish its actual lifetime; hostname/PID guessing cannot.
    script = '\n'.join([
        'import os,socket,sys',
        'from app.config import AppSettings', 'from app.main import create_app',
        'from app.services.admin import initialize_settings',
        'from app.services.admin_scheduling import claim_ai',
        f'settings=AppSettings(_env_file=None,database_url={app.state.settings.database_url!r},runtime_root={str(app.state.settings.runtime_root)!r},worker_enabled=False,analyst_worker_enabled=False)',
        'app=create_app(settings=settings)', 'initialize_settings(app)',
        f'socket.gethostname=lambda: {old_hostname!r}', f'os.getpid=lambda: {os.getpid()}',
        'print(claim_ai(app),flush=True)', 'sys.stdin.read()', 'os._exit(0)',
    ])
    child = subprocess.Popen([sys.executable, '-c', script], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == row.id
        # Another process with the same advertised PID must not release this claim.
        release_lease(app.state.engine, 'ai', row.id)
        recover(app)
        with Session(app.state.engine) as session:
            assert session.get(AnalystJob, row.id).status == 'running'
            assert session.get(AdminLease, ('ai', row.id)) is not None
        child.communicate(timeout=5)
        assert child.returncode == 0
        recover(app)
        with Session(app.state.engine) as session:
            current = session.get(AnalystJob, row.id)
            assert current.status == 'queued'
            assert current.attempts == 1 and current.request_id == row.request_id
            assert session.get(AdminLease, ('ai', row.id)) is None
    finally:
        if child.poll() is None:
            child.communicate(timeout=5)


def test_video_child_lock_prevents_recovery_until_child_finishes(admin_app):
    app, _ = admin_app
    with Session(app.state.engine) as session:
        row = Analysis(owner_id=2, title='video', status='queued', input_manifest_json='{}')
        session.add(row); session.commit(); job_id = row.id
    assert claim_video(app) == job_id
    with Session(app.state.engine) as session:
        saved = session.get(AdminLease, ('video', job_id)).model_dump()
    child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'], stdin=subprocess.PIPE,
                             pass_fds=app.state.video_worker_lock_fds)
    try:
        # Leave the durable claim as a crashed parent would, after closing this
        # process's descriptors. The actual child keeps inherited kernel locks.
        release_lease(app.state.engine, 'video', job_id)
        with Session(app.state.engine) as session:
            session.add(AdminLease(**saved)); session.commit()
        recover(app)
        with Session(app.state.engine) as session:
            assert session.get(AdminLease, ('video', job_id)) is not None
            assert session.get(Analysis, job_id).status == 'queued'
        child.communicate(timeout=5)
        recover(app)
        with Session(app.state.engine) as session:
            assert session.get(AdminLease, ('video', job_id)) is None
            assert session.get(Analysis, job_id).status == 'interrupted'
    finally:
        if child.poll() is None:
            child.communicate(timeout=5)


def test_legacy_foreign_lease_without_lock_proof_stays_untouched(admin_app):
    app, _ = admin_app
    row = seed_job(app, 'report', attempts=1, status='running')
    with Session(app.state.engine) as session:
        session.add(AdminLease(kind='ai', job_id=row.id, pool='ai', pid=999999, hostname='unknown-old-host'))
        session.commit()
    recover(app)
    with Session(app.state.engine) as session:
        assert session.get(AnalystJob, row.id).status == 'running'
        assert session.get(AdminLease, ('ai', row.id)) is not None


def test_rolled_back_claim_releases_kernel_guard(admin_app):
    from sqlalchemy import event
    from app.services.admin_scheduling import claim_ai
    app, _ = admin_app
    row = seed_job(app, 'report')
    saved = []

    def fail_claim_commit(session):
        leases = [obj for obj in session.new if isinstance(obj, AdminLease)]
        if leases:
            saved.append(leases[0].model_dump())
            raise RuntimeError('synthetic commit failure')

    event.listen(Session, 'before_commit', fail_claim_commit)
    try:
        with pytest.raises(RuntimeError, match='synthetic commit failure'):
            claim_ai(app)
    finally:
        event.remove(Session, 'before_commit', fail_claim_commit)
    with Session(app.state.engine) as session:
        assert session.get(AnalystJob, row.id).status == 'queued'
        assert session.get(AdminLease, ('ai', row.id)) is None
        # An abandoned claim identity with no running owner must be recoverable.
        session.add(AdminLease(**saved[0]))
        current = session.get(AnalystJob, row.id); current.status = 'running'
        session.add(current); session.commit()
    recover(app)
    with Session(app.state.engine) as session:
        assert session.get(AnalystJob, row.id).status == 'queued'
        assert session.get(AdminLease, ('ai', row.id)) is None

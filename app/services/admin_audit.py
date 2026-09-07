"""Operator audits share successful writes, and survive rejected-write rollback."""
import json
import re
from contextlib import contextmanager
from copy import deepcopy

from fastapi import HTTPException

from app.admin_models import AdminAudit


def _record(session, *, actor_id, action, target_kind, ids, reason, before, after, status, http_status):
    # Identifiers are metadata; arbitrary rejected input must not become a log/path channel.
    safe_ids = [value for value in ids if type(value) is int or
                isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value)]
    session.add(AdminAudit(actor_id=actor_id, action=action, target_kind=target_kind,
        target_ids_json=json.dumps(safe_ids), reason=reason,
        changes_json=json.dumps({'before':before, 'after':after,
            'outcome':{'status':status, 'http_status':http_status}}, sort_keys=True)))


@contextmanager
def audited_mutation(session, *, actor_id, action, target_kind, ids=(), reason, snapshot, http_status=200):
    """Snapshots contain only fields explicitly selected by the operation's service.

    A rejected operation records identical before/after snapshots: its writes were
    rolled back. No exception detail or arbitrary request body is persisted.
    """
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    before = {}
    common = dict(actor_id=actor_id, action=action, target_kind=target_kind, ids=ids, reason=reason)
    try:
        before = deepcopy(snapshot())
        yield
        session.flush()
        _record(session, **common, before=before, after=snapshot(), status='applied', http_status=http_status)
        session.commit()
    except HTTPException as error:
        session.rollback()
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        _record(session, **common, before=before, after=before, status='rejected', http_status=error.status_code)
        session.commit()
        raise
    except BaseException:
        session.rollback()
        raise

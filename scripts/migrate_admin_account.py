"""Explicit offline account split. Default is a rollback-only dry run.

Stop all admission and workers and drain video/AI/preset queues first. This tool
never executes a schema migration, changes a password of an existing identity,
regenerates content, or reads application credentials from environment files.
"""
import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from sqlalchemy import MetaData, select as sa_select, update
from sqlmodel import Session, select
from app.database import create_database_engine
from app.models import User, Analysis
from app.analyst_models import AnalystJob, AnalystReport, AnalystMessage, AnalystConversation
from app.admin_models import AdminLease, AdminPresetJob
from app.security import normalize_identity, hash_password
from app.services.identities import find_user_by_identity, ensure_user_identities
from app.services.admin import revoke_credentials
from app.services.analyst import digest, pack, PROMPT_VERSION, SESSION_PROMPT_VERSION, COMPARISON_PROMPT_VERSION


def report_rekey(report,payload,old_id,new_id):
    core=dict(owner=old_id,task=report.task_id,facts=payload['facts'],memory=payload['memory'],locale=report.locale,style=report.style,model=report.model)
    if 'report_kind' in payload:
        core.update(kind=payload['report_kind'],prompt=payload.get('prompt_version') or (COMPARISON_PROMPT_VERSION if report.kind=='comparison' else SESSION_PROMPT_VERSION))
        if report.subject_id is not None:
            core['subject_id']=report.subject_id
        if report.kind=='session':
            core['memory']={}
    else:
        core['prompt']=PROMPT_VERSION
    if digest(core)!=report.cache_key or payload.get('cache_key')!=report.cache_key:
        return None
    return digest({**core,'owner':new_id})


def detached_message_accounting(job, payload):
    """Recognize the exact terminal privacy tombstone produced by task deletion.

    Its original request hash stays globally reserved. There is no surviving
    conversation to rekey, and reconstructing deleted provenance is forbidden.
    """
    return (job.status in {'completed', 'failed'} and job.task_id is None and
            job.report_id is None and job.message_id is None and job.error is None and
            isinstance(payload, dict) and set(payload) == {'automatic'} and
            type(payload['automatic']) is bool)


def migrate_account(engine,*,admin_identity,owner_identity='xue@dsb.com',password,dry_run=True):
    admin_identity=normalize_identity(admin_identity)
    owner_identity=normalize_identity(owner_identity)
    if owner_identity!='xue@dsb.com':
        # Other identities are checked for collisions before rejecting unsupported targets.
        with Session(engine) as session:
            if find_user_by_identity(session,owner_identity):
                raise ValueError('Owner identity collision')
        raise ValueError('Owner identity must be xue@dsb.com')
    if not 8<=len(password)<=128:
        raise ValueError('New password must contain 8 to 128 characters')
    with Session(engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        try:
            source=find_user_by_identity(session,admin_identity)
            if not source:
                raise ValueError('Explicit administrator identity not found')
            if find_user_by_identity(session,owner_identity):
                raise ValueError('Owner identity collision')
            from app.services.tasks import RUNNING_STATUSES
            pending=set(RUNNING_STATUSES)|{'queued','uploading'}
            if (session.exec(select(Analysis.id).where(Analysis.status.in_(pending))).first() or
                session.exec(select(AnalystJob.id).where(AnalystJob.status.in_(('queued','running')))).first() or
                session.exec(select(AdminPresetJob.id).where(AdminPresetJob.status.in_(('queued','running')))).first() or
                session.exec(select(AdminLease)).first()):
                raise ValueError('All queues and worker leases must be drained')
            source_id=source.id
            owner=User(username=owner_identity,email=owner_identity,hashed_password=hash_password(password),role='user')
            session.add(owner);session.flush();ensure_user_identities(session,owner);session.flush()
            new_id=owner.id
            jobs=session.exec(select(AnalystJob).where(AnalystJob.owner_id==source_id)).all()
            reports=session.exec(select(AnalystReport).where(AnalystReport.owner_id==source_id)).all()
            key_map={}
            for report in reports:
                candidates=[job for job in jobs if job.report_id==report.id]
                new_key=None
                for job in candidates:
                    try:
                        new_key=report_rekey(report,json.loads(job.payload_json),source_id,new_id)
                    except (KeyError,TypeError,ValueError):
                        continue
                    if new_key:
                        break
                if not new_key:
                    raise ValueError('Cannot validate original report cache provenance; migration stopped')
                if session.exec(select(AnalystReport.id).where(AnalystReport.cache_key==new_key,AnalystReport.id!=report.id)).first():
                    raise ValueError('Report cache collision')
                key_map[report.cache_key]=new_key
                report.cache_key=new_key
                session.add(report)
            for job in jobs:
                payload=json.loads(job.payload_json)
                if payload.get('cache_key') in key_map:
                    payload['cache_key']=key_map[payload['cache_key']]
                    job.payload_json=pack(payload)
                if job.kind=='message' and job.request_id:
                    answer=session.get(AnalystMessage,job.message_id) if job.message_id else None
                    if answer is None:
                        if detached_message_accounting(job, payload):
                            # Only owner_id changes in the reflected transfer below.
                            # Keep counters, usage, timestamps and unique request ID.
                            continue
                        raise ValueError('Cannot validate message dedup provenance')
                    requests=session.exec(select(AnalystMessage).where(AnalystMessage.conversation_id==answer.conversation_id,AnalystMessage.role=='user',AnalystMessage.request_id.is_not(None))).all()
                    match=next((r for r in requests if digest(dict(owner=source_id,conversation=answer.conversation_id,request=r.request_id))==job.request_id),None)
                    if match is None:
                        raise ValueError('Cannot validate message request provenance')
                    new_request=digest(dict(owner=new_id,conversation=answer.conversation_id,request=match.request_id))
                    if session.exec(select(AnalystJob.id).where(AnalystJob.request_id==new_request,AnalystJob.id!=job.id)).first():
                        raise ValueError('Message request collision')
                    job.request_id=new_request
                session.add(job)
            source.role='admin'
            revoke_credentials(session,source)
            session.flush()
            # Reflection includes every owner table, including newer sync/cache ledgers.
            # Identity registry and audit actor IDs intentionally remain with the admin.
            metadata=MetaData()
            metadata.reflect(bind=session.connection())
            counts={}
            for table in metadata.sorted_tables:
                if 'owner_id' not in table.c:
                    continue
                result=session.execute(update(table).where(table.c.owner_id==source_id).values(owner_id=new_id))
                counts[table.name]=result.rowcount
            session.flush()
            for table in metadata.sorted_tables:
                if 'owner_id' in table.c and session.execute(sa_select(table.c.owner_id).where(table.c.owner_id==source_id).limit(1)).first():
                    raise ValueError('Owner continuity validation failed')
            result=dict(dry_run=dry_run,admin_id=source_id,owner_id=new_id,transferred=counts,rekeyed_reports=len(key_map))
            if dry_run:
                session.rollback()
            else:
                session.commit()
            return result
        except Exception:
            session.rollback()
            raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True,help='Explicit local SQLite database file; schema must already be upgraded')
    parser.add_argument('--admin-identity',required=True)
    parser.add_argument('--password-stdin',action='store_true',help='Read the new owner password from stdin')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run',action='store_true',help='Validate all writes then roll back (default)')
    mode.add_argument('--apply',action='store_true',help='Apply the validated split to the explicit offline database')
    args=parser.parse_args(argv)
    path=Path(args.database).expanduser().resolve(strict=True)
    password=sys.stdin.readline().rstrip('\r\n') if args.password_stdin else getpass.getpass('New xue@dsb.com password: ')
    engine=create_database_engine('sqlite:///'+str(path))
    try:
        result=migrate_account(engine,admin_identity=args.admin_identity,password=password,dry_run=not args.apply)
    except (ValueError,KeyError) as error:
        parser.exit(2,str(error)+'\n')
    finally:
        engine.dispose()
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    main()

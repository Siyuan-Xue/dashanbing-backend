import json
import importlib
from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.models import Analysis, User, ApiKey, utc_now
from app.analyst_models import AnalystReport, AnalystJob, AnalystConversation, AnalystMessage, TrainingProfile, TaskSubject, TrainingObservation
from app.services.analyst import digest, pack, SESSION_PROMPT_VERSION
from tests.test_admin_auth import admin_app, login


def seed_transfer(app):
    with Session(app.state.engine) as s:
        task=Analysis(owner_id=1,title='retained',status='completed',input_manifest_json='{}')
        s.add(task);s.flush()
        facts={'subjects':[],'evidence':[]}
        core={'owner':1,'task':task.id,'kind':'session','facts':facts,'memory':{},'locale':'zh','style':'coach','model':'glm-5.3','prompt':SESSION_PROMPT_VERSION}
        report=AnalystReport(owner_id=1,task_id=task.id,cache_key=digest(core),status='completed',body_json='{"private":"unchanged"}',model='glm-5.3')
        s.add(report);s.flush()
        job=AnalystJob(owner_id=1,task_id=task.id,kind='report',report_id=report.id,status='completed',payload_json=pack({'cache_key':report.cache_key,'facts':facts,'memory':{},'locale':'zh','style':'coach','report_kind':'session','subject_id':None,'prompt_version':SESSION_PROMPT_VERSION}))
        conversation=AnalystConversation(owner_id=1,task_id=task.id)
        s.add(conversation);s.flush()
        question=AnalystMessage(owner_id=1,conversation_id=conversation.id,role='user',content='private unchanged question',status='completed',request_id='original')
        answer=AnalystMessage(owner_id=1,conversation_id=conversation.id,role='assistant',content='private unchanged answer',status='completed')
        s.add_all([question,answer]);s.flush()
        chat=AnalystJob(owner_id=1,task_id=task.id,kind='message',message_id=answer.id,status='completed',request_id=digest({'owner':1,'conversation':conversation.id,'request':'original'}),payload_json=pack({'question':'private unchanged question'}))
        profile=TrainingProfile(owner_id=1,kind='player',name='private profile')
        s.add(profile);s.flush()
        s.add(TaskSubject(task_id=task.id,subject_id='p1',owner_id=1,profile_id=profile.id))
        s.add(TrainingObservation(owner_id=1,profile_id=profile.id,source_task_id=task.id,fingerprint='abc',mode='full'))
        key=ApiKey(owner_id=1,name='old',digest='a'*64,prefix='dsb_live_',last_four='1234',expires_at=utc_now()+timedelta(days=1))
        s.add_all([job,chat,key]);s.commit()
        return task.id,report.id,job.id,chat.id,conversation.id,core


def test_owner_migration_dry_run_then_preserves_body_and_dedup(admin_app):
    app,_=admin_app
    ids=seed_transfer(app)
    migration=importlib.import_module('scripts.migrate_admin_account')
    with Session(app.state.engine) as s:
        before=s.get(AnalystReport,ids[1]).model_dump()
    result=migration.migrate_account(app.state.engine,admin_identity='admin',owner_identity='xue@dsb.com',password='secure-new-password',dry_run=True)
    assert result['dry_run'] is True
    with Session(app.state.engine) as s:
        assert s.exec(select(User).where(User.username=='xue@dsb.com')).first() is None
        assert s.get(AnalystReport,ids[1]).model_dump()==before
    result=migration.migrate_account(app.state.engine,admin_identity='admin',owner_identity='xue@dsb.com',password='secure-new-password',dry_run=False)
    new_id=result['owner_id']
    with Session(app.state.engine) as s:
        assert s.get(User,1).role=='admin' and s.get(User,1).session_version==1
        assert s.get(User,new_id).role=='user'
        report=s.get(AnalystReport,ids[1]);job=s.get(AnalystJob,ids[2]);chat=s.get(AnalystJob,ids[3])
        assert report.body_json==before['body_json'] and report.created_at==before['created_at']
        assert report.owner_id==new_id and report.cache_key==digest({**ids[5],'owner':new_id})
        assert json.loads(job.payload_json)['cache_key']==report.cache_key
        assert chat.request_id==digest({'owner':new_id,'conversation':ids[4],'request':'original'})
        assert all(key.revoked_at is not None for key in s.exec(select(ApiKey)))
        for cls in (Analysis,TrainingProfile,TaskSubject,TrainingObservation,AnalystConversation,AnalystMessage,AnalystJob):
            assert not s.exec(select(cls).where(cls.owner_id==1)).all()


def test_migration_collisions_and_live_queues_stop_without_writes(admin_app):
    app,_=admin_app
    migration=importlib.import_module('scripts.migrate_admin_account')
    with pytest.raises(ValueError,match='collision'):
        migration.migrate_account(app.state.engine,admin_identity='admin',owner_identity='normal@example.com',password='secure-password',dry_run=False)
    with Session(app.state.engine) as s:
        s.add(Analysis(owner_id=1,title='queued',status='queued',input_manifest_json='{}'));s.commit()
    with pytest.raises(ValueError,match='drained'):
        migration.migrate_account(app.state.engine,admin_identity='admin',owner_identity='xue@dsb.com',password='secure-password',dry_run=True)


def test_admin_schema_migration_adds_user_defaults_without_promotion(tmp_path,monkeypatch):
    from alembic import command
    from alembic.config import Config
    from app.database import create_database_engine
    path=tmp_path/'schema.db'
    monkeypatch.setenv('BASKETBALL_DATABASE_URL',f'sqlite:///{path}')
    config=Config('alembic.ini')
    command.upgrade(config,'20260905_0011')
    engine=create_database_engine(f'sqlite:///{path}')
    with engine.begin() as c:
        c.exec_driver_sql("INSERT INTO user (username,hashed_password,is_active,created_at) VALUES ('old','hash',1,CURRENT_TIMESTAMP)")
    command.upgrade(config,'20260907_0012')
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT role, session_version FROM user').one()==('user',0)
        assert c.exec_driver_sql("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='admin_settings'").scalar()==1


def test_migration_preserves_detached_accounting_from_real_business_task_deletion(admin_app):
    from app.admin_models import AdminAttempt
    app, client = admin_app
    ids = seed_transfer(app)
    with Session(app.state.engine) as session:
        # Model the legacy business account that is being split, then use the real
        # ordinary DELETE route so the migration fixture matches privacy scrubbing.
        source = session.get(User, 1); source.role = 'user'; session.add(source)
        job = session.get(AnalystJob, ids[3]); job.attempts = 2; job.usage_json = '{"total_tokens":41}'
        session.add(job)
        session.add(AdminAttempt(kind='ai', job_id=job.id, owner_id=1, repair=False))
        session.commit()
    headers = login(client)
    assert client.delete('/api/v1/tasks/' + ids[0], headers=headers).status_code == 204
    with Session(app.state.engine) as session:
        assert session.get(Analysis, ids[0]) is None
        assert session.exec(select(AnalystMessage)).all() == []
        assert session.exec(select(AnalystConversation)).all() == []
        before = session.get(AnalystJob, ids[3]).model_dump()
        assert before['task_id'] is None and before['message_id'] is None
        assert json.loads(before['payload_json']) == {'automatic':False}
        attempt_before = session.exec(select(AdminAttempt)).one().model_dump()
    migration = importlib.import_module('scripts.migrate_admin_account')
    args = dict(admin_identity='admin', password='secure-new-password')
    migration.migrate_account(app.state.engine, **args, dry_run=True)
    with Session(app.state.engine) as session:
        assert session.get(AnalystJob, ids[3]).model_dump() == before
        assert session.exec(select(User).where(User.username=='xue@dsb.com')).first() is None
    result = migration.migrate_account(app.state.engine, **args, dry_run=False)
    with Session(app.state.engine) as session:
        assert session.get(AnalystJob, ids[3]).model_dump() == {**before, 'owner_id':result['owner_id']}
        assert session.exec(select(AdminAttempt)).one().model_dump() == {**attempt_before, 'owner_id':result['owner_id']}
        assert session.exec(select(AnalystMessage)).all() == []
        assert session.exec(select(AnalystConversation)).all() == []
    assert client.get('/api/v1/users/me', headers=headers).status_code == 401


@pytest.mark.parametrize('payload,linked', [({}, False), ({'automatic':'false'}, False),
    ({'automatic':False, 'question':'private'}, False), ({'automatic':False}, True)])
def test_migration_rejects_unrecognized_missing_message_provenance(admin_app, payload, linked):
    app, _ = admin_app
    with Session(app.state.engine) as session:
        job = AnalystJob(owner_id=1, kind='message', status='failed', request_id='opaque-request',
            message_id='missing-answer' if linked else None, payload_json=json.dumps(payload))
        session.add(job); session.commit(); job_id = job.id
    migration = importlib.import_module('scripts.migrate_admin_account')
    with pytest.raises(ValueError, match='provenance'):
        migration.migrate_account(app.state.engine, admin_identity='admin', password='secure-new-password', dry_run=False)
    with Session(app.state.engine) as session:
        assert session.get(AnalystJob, job_id).owner_id == 1
        assert session.exec(select(User).where(User.username=='xue@dsb.com')).first() is None


def test_detached_accounting_tombstone_still_blocks_live_message_rekey_collision(admin_app):
    app, _ = admin_app
    ids = seed_transfer(app)
    with Session(app.state.engine) as session:
        new_owner_id = max(session.exec(select(User.id)).all()) + 1
        collision = digest({'owner':new_owner_id, 'conversation':ids[4], 'request':'original'})
        session.add(AnalystJob(owner_id=1, kind='message', status='completed', request_id=collision,
                              payload_json='{"automatic":false}'))
        session.commit()
    migration = importlib.import_module('scripts.migrate_admin_account')
    with pytest.raises(ValueError, match='collision'):
        migration.migrate_account(app.state.engine, admin_identity='admin', password='secure-new-password', dry_run=False)
    with Session(app.state.engine) as session:
        assert session.exec(select(User).where(User.username=='xue@dsb.com')).first() is None
        assert session.get(AnalystJob, ids[3]).request_id == digest({'owner':1, 'conversation':ids[4], 'request':'original'})

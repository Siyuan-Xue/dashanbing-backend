"""Queue/report/chat regressions using real SQLite, facts and API routes.

Only the external provider and background scheduling are replaced. Retry clocks
are advanced through persisted availability rather than sleeps or network calls.
"""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlmodel import Session, select
from starlette.requests import Request

from app.analyst_models import AnalystConversation, AnalystJob, AnalystMessage, AnalystReport
from app.config import AppSettings
from app.models import Analysis, User
from app.services import analyst
from app.services.glm import GlmError, GlmJsonResult, GlmTextDelta, GlmUsage


USAGE = {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}
FAKE_KEY = "not-a-real-glm-key-for-integration-tests"


class ScriptedProvider:
    def __init__(self, *, reports=(), streams=()):
        self.reports = list(reports)
        self.streams = list(streams)
        self.calls = []

    async def complete_json(self, messages, *, request_id):
        self.calls.append(("report", request_id, deepcopy(messages)))
        assert self.reports, "Unexpected report provider call"
        result = self.reports.pop(0)
        if isinstance(result, Exception):
            raise result
        return GlmJsonResult(data=deepcopy(result), usage=dict(USAGE))

    async def stream(self, messages, *, request_id):
        self.calls.append(("message", request_id, deepcopy(messages)))
        assert self.streams, "Unexpected chat provider call"
        for event in self.streams.pop(0):
            if isinstance(event, Exception):
                raise event
            yield event


class PausingProvider:
    """Pause after a request starts (or after one persisted stream delta)."""

    def __init__(self, body, *, prefix="First part ", ending="finished", error=None):
        self.body = body
        self.prefix = prefix
        self.ending = ending
        self.error = error
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = []

    async def complete_json(self, messages, *, request_id):
        self.calls.append(request_id)
        self.started.set()
        await self.release.wait()
        if self.error is not None:
            raise self.error
        return GlmJsonResult(data=deepcopy(self.body), usage=dict(USAGE))

    async def stream(self, messages, *, request_id):
        self.calls.append(request_id)
        yield GlmTextDelta(text=self.prefix)
        self.started.set()
        await self.release.wait()
        if self.error is not None:
            raise self.error
        yield GlmTextDelta(text=self.ending)
        yield GlmUsage(usage=dict(USAGE))


@pytest.fixture
def job_client(tmp_path):
    # Local fixture avoids the API fixture's environment-dependent key and
    # automatic supervisor startup. Both are set before the lifespan starts.
    from app.main import create_app

    settings = AppSettings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'jobs.db'}",
        runtime_root=tmp_path / "runtime",
        sample_root=tmp_path / "samples",
        admin_username="admin",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        worker_enabled=False,
        auto_create_schema=True,
        min_free_storage_gb=0,
    ).model_copy(update={
        "glm_api_key": SecretStr(FAKE_KEY),
        "analyst_worker_enabled": False,
        "analyst_daily_limit": 100,
    })
    app = create_app(settings=settings)
    app.state.glm_client = ScriptedProvider()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/login/access-token", data={
            "username": "admin", "password": "correct-password",
        })
        assert response.status_code == 200, response.text
        with Session(app.state.engine) as session:
            owner = session.exec(select(User).where(User.username == "admin")).one()
            task = Analysis(title="Training", owner_id=owner.id, status="completed",
                            progress=100, input_manifest_json="{}")
            session.add(task)
            session.commit()
            session.refresh(task)
            client.task_id = task.id
            client.owner_id = owner.id
        output = app.state.storage.analysis_root(client.task_id) / "output"
        output.mkdir(parents=True)
        (output / "report.json").write_text(json.dumps({
            "clips": [
                {"clip_id": "stu_03:0", "student_id": "stu_03", "action_type": "jump_shot",
                 "start_ms": 1000, "release_ms": 1500, "end_ms": 2000},
                {"clip_id": "stu_04:0", "student_id": "stu_04", "action_type": "jump_shot",
                 "start_ms": 3000, "release_ms": 3500, "end_ms": 4000},
            ],
            "shot_outcomes": [
                {"clip_id": "stu_03:0", "student_id": "stu_03", "made": True},
                {"clip_id": "stu_04:0", "student_id": "stu_04", "made": False},
            ],
            "shot_stats": {"attempts": 2, "makes": 1, "misses": 1, "undetermined": 0},
        }), encoding="utf-8")
        (output / "summary.json").write_text('{"student_ids":["stu_03","stu_04"]}', encoding="utf-8")
        yield client


@pytest.fixture
def facts(job_client):
    from app.services.analyst_facts import load_task_facts

    with Session(job_client.app.state.engine) as session:
        return load_task_facts(job_client.app, session.get(Analysis, job_client.task_id))


@pytest.fixture
def report_body(facts):
    first = facts.evidence[0]
    return {
        "summary": "Two recorded shots, one make",
        "highlights": [{"text": "One recorded make", "evidence_ids": [first.id]}],
        "players": [{"subject_id": first.subject_id, "text": "This shot was recorded as made",
                     "evidence_ids": [first.id]}],
        "suggestions": ["Repeat the drill and review the next session"],
    }


def all_rows(client, model):
    with Session(client.app.state.engine) as session:
        return list(session.exec(select(model)).all())


def get_row(client, model, row_id):
    with Session(client.app.state.engine) as session:
        return session.get(model, row_id)


def report_url(client):
    return f"/api/v1/tasks/{client.task_id}/analyst/report"


def request_report(client, *, regenerate=False):
    response = client.post(report_url(client), json={"locale": "en", "style": "coach", "regenerate": regenerate})
    assert response.status_code == 202, response.text
    jobs = [job for job in all_rows(client, AnalystJob) if job.kind == "report"]
    return max(jobs, key=lambda job: job.created_at)


def create_conversation(client, **kwargs):
    response = client.post("/api/v1/analyst/conversations", json={
        "task_id": client.task_id, "locale": "en", "style": "coach", **kwargs,
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def submit(client, conversation_id, *, content="What should I practise?", request_id="chat-request"):
    return client.post(f"/api/v1/analyst/conversations/{conversation_id}/messages", json={
        "content": content, "request_id": request_id,
    })


def request_chat(client):
    conversation_id = create_conversation(client)
    response = submit(client, conversation_id)
    assert response.status_code == 202, response.text
    return get_row(client, AnalystJob, response.json()["job_id"]), conversation_id


def make_due(client, job_id):
    from app.analyst_models import AnalystProviderState
    with Session(client.app.state.engine) as session:
        job = session.get(AnalystJob, job_id)
        job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.add(job)
        provider = session.get(AnalystProviderState, "glm")
        if provider:
            provider.available_at = job.available_at
            session.add(provider)
        session.commit()


def run_once(client):
    return asyncio.run(analyst.AnalystSupervisor(client.app).run_once())


def assert_video_completed(client):
    task = get_row(client, Analysis, client.task_id)
    assert task.status == "completed"
    assert task.progress == 100


def assert_session_variants(client):
    reports = all_rows(client, AnalystReport)
    assert len(reports) == 6
    assert {(row.subject_id, row.style, row.locale, row.kind) for row in reports} == {
        (subject, style, "zh", "session")
        for subject in (None, "player_1", "player_2") for style in ("coach", "roast")
    }
    jobs = [job for job in all_rows(client, AnalystJob) if job.kind == "report"]
    assert len(jobs) == 6
    assert {job.report_id for job in jobs} == {row.id for row in reports}
    assert len({job.request_id for job in jobs}) == 6
    return sorted(jobs, key=lambda job: job.created_at)


def queued_report_bodies(client, facts, body):
    """Script valid responses for the real pending jobs, including player 2."""
    bodies = []
    jobs = sorted(all_rows(client, AnalystJob), key=lambda job: job.created_at)
    for job in jobs:
        if job.kind != "report" or job.status != "queued":
            continue
        subject_id = get_row(client, AnalystReport, job.report_id).subject_id
        if subject_id is None:
            bodies.append(deepcopy(body))
            continue
        evidence = next(item for item in facts.evidence if item.subject_id == subject_id)
        bodies.append({
            "summary": "One recorded shot for this player",
            "highlights": [{"text": "Review this recorded shot", "evidence_ids": [evidence.id]}],
            "players": [{"subject_id": subject_id, "text": "One shot was recorded",
                         "evidence_ids": [evidence.id]}],
            "suggestions": ["Repeat the drill and review the next session"],
        })
    return bodies


def test_automatic_enqueue_participates_in_completion_transaction_and_deduplicates(job_client):
    client = job_client
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, client.task_id)
        task.status = "visualizing"
        session.add(task)
        session.commit()
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, client.task_id)
        task.status = "completed"
        session.add(task)
        analyst.enqueue_completed(session, task, enabled=True)
        analyst.enqueue_completed(session, task, enabled=True)
        session.flush()
        assert len(session.exec(select(AnalystJob)).all()) == 1
        with Session(client.app.state.engine) as observer:
            assert observer.get(Analysis, client.task_id).status == "visualizing"
            assert observer.exec(select(AnalystJob)).all() == []
        session.rollback()
    assert get_row(client, Analysis, client.task_id).status == "visualizing"
    assert all_rows(client, AnalystJob) == []

    from app.services.worker import _complete
    # Completion must not depend on reading the not-yet-consumed facts artifact.
    output = client.app.state.storage.analysis_root(client.task_id) / "output"
    (output / "report.json").unlink()
    _complete(client.app, client.task_id)
    _complete(client.app, client.task_id)
    jobs = all_rows(client, AnalystJob)
    assert len(jobs) == 1
    assert jobs[0].kind == "prepare"
    assert jobs[0].status == "queued"
    assert json.loads(jobs[0].payload_json) == {"automatic": True}
    assert client.app.state.glm_client.calls == []
    assert_video_completed(client)


@pytest.mark.parametrize("status,enabled", [("completed", False), ("visualizing", True), ("canceled", True)])
def test_automatic_enqueue_ignores_disabled_or_unfinished_tasks(job_client, status, enabled):
    with Session(job_client.app.state.engine) as session:
        task = session.get(Analysis, job_client.task_id)
        task.status = status
        analyst.enqueue_completed(session, task, enabled=enabled)
        session.commit()
    assert all_rows(job_client, AnalystJob) == []


def test_automatic_prepare_persists_valid_report_usage_and_keeps_video_completed(job_client, report_body, facts):
    client = job_client
    provider = ScriptedProvider(reports=[report_body])
    client.app.state.glm_client = provider
    with Session(client.app.state.engine) as session:
        analyst.enqueue_completed(session, session.get(Analysis, client.task_id), enabled=True)
        session.commit()
    assert run_once(client) is True
    jobs = all_rows(client, AnalystJob)
    assert sorted((job.kind, job.status) for job in jobs) == [("prepare", "completed")] + [("report", "queued")] * 6
    report_jobs = assert_session_variants(client)
    assert provider.calls == []
    provider.reports = queued_report_bodies(client, facts, report_body)
    for report_job in report_jobs:
        assert run_once(client) is True
        report_job = get_row(client, AnalystJob, report_job.id)
        report = get_row(client, AnalystReport, report_job.report_id)
        assert report.status == report_job.status == "completed"
        assert json.loads(report_job.usage_json) == USAGE
        assert report_job.attempts == 1
        assert json.loads(report_job.payload_json)["automatic"] is True
    assert run_once(client) is False
    report = next(row for row in all_rows(client, AnalystReport) if row.subject_id is None and row.style == "coach")
    assert json.loads(report.body_json)["players"] == report_body["players"]
    assert [call[1] for call in provider.calls] == [job.request_id for job in report_jobs]
    for call, job in zip(provider.calls, report_jobs):
        payload = json.loads(job.payload_json)
        assert payload['memory'] == {}
        if payload['subject_id'] is not None:
            assert {item['id'] for item in payload['facts']['subjects']} == {payload['subject_id']}
            assert {item['subject_id'] for item in payload['facts']['evidence']} == {payload['subject_id']}
            other_player = 'player_2' if payload['subject_id'] == 'player_1' else 'player_1'
            assert other_player not in json.dumps(call)
    public = client.get(report_url(client)).json()
    assert public["report"]["summary"] == report_body["summary"]
    assert public["report"]["model"] == "glm-5.3"
    assert "stu_03" not in json.dumps(provider.calls)
    assert FAKE_KEY not in json.dumps(provider.calls)
    assert_video_completed(client)


@pytest.mark.parametrize("defect", ["unknown_evidence", "unknown_player", "different_player", "invalid_schema"])
def test_invalid_report_retries_then_fails_without_persisting_body(job_client, report_body, facts, defect, caplog):
    client = job_client
    body = deepcopy(report_body)
    if defect == "unknown_evidence":
        body["players"][0]["evidence_ids"] = [facts.evidence[0].id + "-missing"]
    elif defect == "unknown_player":
        body["players"][0]["subject_id"] = "unknown-player"
    elif defect == "different_player":
        body["players"][0]["evidence_ids"] = [facts.evidence[1].id]
    else:
        body["summary"] = []
    provider = ScriptedProvider(reports=[body, body, body])
    client.app.state.glm_client = provider
    job = request_report(client)
    for attempt in (1, 2, 3):
        make_due(client, job.id)
        assert run_once(client) is True
        current = get_row(client, AnalystJob, job.id)
        report = get_row(client, AnalystReport, job.report_id)
        assert current.attempts == attempt
        assert current.status == report.status == ("failed" if attempt == 3 else "queued")
        assert report.body_json == "{}"
        assert json.loads(current.usage_json) == {}
        assert_video_completed(client)
    assert run_once(client) is False
    assert len(provider.calls) == 3
    assert len({call[1] for call in provider.calls}) == 1
    assert get_row(client, AnalystReport, job.report_id).error
    assert FAKE_KEY not in caplog.text


@pytest.mark.parametrize("kind", ["report", "message"])
@pytest.mark.parametrize("code,status", [("rate_limited", 429), ("timeout", None)])
def test_transient_provider_failure_retries_same_request_and_records_success_usage(job_client, report_body, kind, code, status):
    client = job_client
    error = GlmError(code, retryable=True, status_code=status)
    provider = ScriptedProvider(reports=[error, report_body], streams=[
        [GlmTextDelta(text="Discard this partial answer"), error],
        [GlmTextDelta(text="A complete answer"), GlmUsage(usage=dict(USAGE))],
    ])
    client.app.state.glm_client = provider
    job = request_report(client) if kind == "report" else request_chat(client)[0]
    assert run_once(client) is True
    failed_attempt = get_row(client, AnalystJob, job.id)
    assert failed_attempt.status == "queued"
    assert failed_attempt.attempts == 1
    assert failed_attempt.available_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
    assert run_once(client) is False
    if kind == "message":
        partial = get_row(client, AnalystMessage, job.message_id)
        assert partial.content == ""
        assert partial.status == "queued"
        assert json.loads(partial.citations_json) == []
    make_due(client, job.id)
    assert run_once(client) is True
    completed = get_row(client, AnalystJob, job.id)
    assert completed.status == "completed"
    assert completed.attempts == 2
    assert json.loads(completed.usage_json) == USAGE
    assert provider.calls[0][1] == provider.calls[1][1] == job.request_id
    if kind == "message":
        assert len(all_rows(client, AnalystMessage)) == 2
        assert get_row(client, AnalystMessage, job.message_id).content == "A complete answer"
    assert_video_completed(client)


def test_no_key_prevents_manual_jobs_and_automatic_enqueue(job_client):
    client = job_client
    conversation_id = create_conversation(client)
    client.app.state.settings = client.app.state.settings.model_copy(update={"glm_api_key": SecretStr("")})
    assert client.get(report_url(client)).json()["status"] == "disabled"
    assert client.post(report_url(client), json={}).status_code == 503
    assert submit(client, conversation_id).status_code == 503
    from app.services.worker import _complete
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, client.task_id)
        task.status = "visualizing"
        session.add(task)
        session.commit()
    _complete(client.app, client.task_id)
    assert all_rows(client, AnalystJob) == []
    assert all_rows(client, AnalystMessage) == []
    assert all_rows(client, AnalystReport) == []
    assert client.app.state.glm_client.calls == []
    assert_video_completed(client)


def test_manual_daily_quota_covers_regeneration_and_chat_but_excludes_automatic_and_duplicates(job_client, report_body):
    client = job_client
    client.app.state.settings = client.app.state.settings.model_copy(update={"analyst_daily_limit": 2})
    client.app.state.glm_client = ScriptedProvider(reports=[report_body, report_body], streams=[
        [GlmTextDelta(text="A complete answer"), GlmUsage(usage=dict(USAGE))],
    ])
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, client.task_id)
        analyst.request_report(client.app, session, task, locale="en", automatic=True)
        session.commit()
    assert run_once(client)
    cached = client.post(report_url(client), json={"locale": "en"})
    assert cached.status_code == 202 and cached.json()["status"] == "completed"
    regeneration = request_report(client, regenerate=True)
    duplicate = request_report(client, regenerate=True)
    assert duplicate.id == regeneration.id
    assert run_once(client)
    conversation_id = create_conversation(client)
    accepted = submit(client, conversation_id)
    assert accepted.status_code == 202, accepted.text
    repeated = submit(client, conversation_id)
    assert repeated.status_code == 202
    assert repeated.json() == accepted.json()
    assert submit(client, conversation_id, content="A different question").status_code == 409
    assert submit(client, conversation_id, request_id="parallel-request").status_code == 409
    assert run_once(client)
    assert submit(client, conversation_id).json() == accepted.json()
    assert submit(client, conversation_id, request_id="new-request").status_code == 429
    assert client.post(report_url(client), json={"locale": "en", "regenerate": True}).status_code == 429
    jobs = all_rows(client, AnalystJob)
    assert len(jobs) == 3
    assert sum(not json.loads(job.payload_json).get("automatic") for job in jobs) == 2
    assert len(all_rows(client, AnalystMessage)) == 2
    assert_video_completed(client)


def test_prior_day_jobs_do_not_consume_todays_quota_and_request_ids_are_conversation_scoped(job_client):
    client = job_client
    client.app.state.settings = client.app.state.settings.model_copy(update={"analyst_daily_limit": 1})
    first, first_conversation = request_chat(client)
    with Session(client.app.state.engine) as session:
        job = session.get(AnalystJob, first.id)
        job.created_at = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
        session.add(job)
        session.commit()
    second_conversation = create_conversation(client)
    second = submit(client, second_conversation)
    assert second.status_code == 202, second.text
    assert second.json()["job_id"] != first.id
    assert second.json()["message_id"] != first.message_id
    repeated = submit(client, first_conversation)
    assert repeated.status_code == 202
    assert repeated.json()["job_id"] == first.id
    assert len(all_rows(client, AnalystJob)) == 2


def test_valid_chat_citations_use_the_actual_facts_namespace(job_client, facts):
    client = job_client
    evidence_id = facts.evidence[0].id
    text = f"The recorded shot was made [{evidence_id}]"
    client.app.state.glm_client = ScriptedProvider(streams=[
        [GlmTextDelta(text=text), GlmUsage(usage=dict(USAGE))],
    ])
    job, conversation_id = request_chat(client)
    assert run_once(client)
    message = get_row(client, AnalystMessage, job.message_id)
    assert message.status == "completed"
    assert message.content == text
    assert json.loads(message.citations_json) == [evidence_id]
    public = client.get(f"/api/v1/analyst/conversations/{conversation_id}").json()
    assert public["messages"][-1]["citations"] == [evidence_id]
    assert json.loads(get_row(client, AnalystJob, job.id).usage_json) == USAGE


def test_unknown_chat_reference_retries_then_fails(job_client, facts):
    client = job_client
    unknown_id = facts.evidence[0].id + "_nonexistent"
    client.app.state.glm_client = ScriptedProvider(streams=[
        [GlmTextDelta(text=f"Unsupported claim [{unknown_id}]"), GlmUsage(usage=dict(USAGE))]
        for _ in range(3)
    ])
    job, _ = request_chat(client)
    for attempt in (1, 2, 3):
        make_due(client, job.id)
        assert run_once(client)
        current = get_row(client, AnalystJob, job.id)
        assert current.status == ("failed" if attempt == 3 else "queued")
        assert current.attempts == attempt
    message = get_row(client, AnalystMessage, job.message_id)
    assert message.status == "failed"
    assert unknown_id not in message.content
    assert json.loads(message.citations_json) == []


async def sse_messages_once(client, conversation_id):
    """Read one snapshot directly: TestClient buffers unbounded SSE responses."""
    from app.api.routes.analyst import conversation_events

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request({"type": "http", "app": client.app}, receive=receive)
    with Session(client.app.state.engine) as session:
        response = conversation_events(conversation_id, request, session, session.get(User, client.owner_id))
        messages = []
        try:
            for _ in range(2):
                frame = await asyncio.wait_for(anext(response.body_iterator), timeout=2)
                data = next(line[6:] for line in frame.splitlines() if line.startswith("data: "))
                messages.append(json.loads(data))
        finally:
            await response.body_iterator.aclose()
        return messages


def test_partial_answer_reconnect_reads_persisted_state_and_later_completion(job_client, report_body):
    client = job_client
    job, conversation_id = request_chat(client)

    async def run():
        provider = PausingProvider(report_body)
        client.app.state.glm_client = provider
        running = asyncio.create_task(analyst.AnalystSupervisor(client.app).run_once())
        try:
            await asyncio.wait_for(provider.started.wait(), timeout=2)
            saved = get_row(client, AnalystMessage, job.message_id)
            assert saved.status == "running"
            assert saved.content == "First part "
            assert saved.revision > 0
            first_connection = await sse_messages_once(client, conversation_id)
            reconnected = await sse_messages_once(client, conversation_id)
            assert first_connection == reconnected
            assert reconnected[-1]["content"] == "First part "
            assert reconnected[-1]["status"] == "running"
        finally:
            provider.release.set()
            await asyncio.wait_for(running, timeout=2)
        assert get_row(client, AnalystMessage, job.message_id).content == "First part finished"
        assert get_row(client, AnalystMessage, job.message_id).status == "completed"
        assert json.loads(get_row(client, AnalystJob, job.id).usage_json) == USAGE

    asyncio.run(run())
    completed_events = client.get(f"/api/v1/analyst/conversations/{conversation_id}/events")
    assert completed_events.status_code == 200
    assert "First part finished" in completed_events.text
    assert "event: done" in completed_events.text


@pytest.mark.parametrize("kind", ["report", "message"])
def test_cancellation_and_restart_recover_running_job_without_duplicate_rows(job_client, report_body, facts, kind, monkeypatch):
    client = job_client
    job = request_report(client) if kind == "report" else request_chat(client)[0]

    async def parked_loop(self):
        await asyncio.Event().wait()

    monkeypatch.setattr(analyst.AnalystSupervisor, "_loop", parked_loop)

    async def run():
        provider = PausingProvider(report_body, prefix=f"First part [{facts.evidence[0].id}] ")
        client.app.state.glm_client = provider
        running = asyncio.create_task(analyst.AnalystSupervisor(client.app).run_once())
        try:
            await asyncio.wait_for(provider.started.wait(), timeout=2)
        finally:
            running.cancel()
            with pytest.raises(asyncio.CancelledError):
                await running
        interrupted = get_row(client, AnalystJob, job.id)
        assert interrupted.status == "running"
        assert interrupted.attempts == 1
        restarted = analyst.AnalystSupervisor(client.app)
        await restarted.start()
        try:
            assert get_row(client, AnalystJob, job.id).status == "queued"
            if kind == "report":
                assert get_row(client, AnalystReport, job.report_id).status == "queued"
            else:
                reset = get_row(client, AnalystMessage, job.message_id)
                assert reset.status == "queued"
                assert reset.content == ""
                assert json.loads(reset.citations_json) == []
            client.app.state.glm_client = ScriptedProvider(reports=[report_body], streams=[
                [GlmTextDelta(text="Recovered answer"), GlmUsage(usage=dict(USAGE))],
            ])
            assert await restarted.run_once()
        finally:
            await restarted.stop()
        complete = get_row(client, AnalystJob, job.id)
        assert complete.status == "completed"
        assert complete.attempts == 2
        jobs = all_rows(client, AnalystJob)
        assert [row.id for row in jobs if row.kind != "prepare"] == [job.id]
        # Startup separately queues preparation of the default Chinese collection.
        assert len([row for row in jobs if row.kind == "prepare"]) == 1
        assert client.app.state.glm_client.calls[0][1] == job.request_id
        if kind == "message":
            assert len(all_rows(client, AnalystMessage)) == 2
            assert get_row(client, AnalystMessage, job.message_id).content == "Recovered answer"
        assert_video_completed(client)
    asyncio.run(run())


def test_two_supervisors_cannot_claim_the_same_running_job(job_client, report_body):
    client = job_client
    job = request_report(client)

    async def run():
        provider = PausingProvider(report_body)
        client.app.state.glm_client = provider
        first = asyncio.create_task(analyst.AnalystSupervisor(client.app).run_once())
        try:
            await asyncio.wait_for(provider.started.wait(), timeout=2)
            assert await analyst.AnalystSupervisor(client.app).run_once() is False
        finally:
            provider.release.set()
            await asyncio.wait_for(first, timeout=2)
        assert provider.calls == [job.request_id]
        assert get_row(client, AnalystJob, job.id).attempts == 1
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["report", "message"])
def test_deleted_job_while_provider_waits_cannot_be_resurrected(job_client, report_body, kind):
    client = job_client
    job = request_report(client) if kind == "report" else request_chat(client)[0]
    model, row_id = (AnalystReport, job.report_id) if kind == "report" else (AnalystMessage, job.message_id)

    async def run():
        provider = PausingProvider(report_body)
        client.app.state.glm_client = provider
        running = asyncio.create_task(analyst.AnalystSupervisor(client.app).run_once())
        try:
            await asyncio.wait_for(provider.started.wait(), timeout=2)
            with Session(client.app.state.engine) as session:
                session.delete(session.get(AnalystJob, job.id))
                session.delete(session.get(model, row_id))
                session.commit()
        finally:
            provider.release.set()
            await asyncio.wait_for(running, timeout=2)
        assert get_row(client, AnalystJob, job.id) is None
        assert get_row(client, model, row_id) is None
        assert_video_completed(client)
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["report", "message"])
def test_task_deletion_while_provider_waits_cannot_leave_completed_analyst_orphans(job_client, report_body, kind):
    client = job_client
    job = request_report(client) if kind == "report" else request_chat(client)[0]

    async def run():
        provider = PausingProvider(report_body)
        client.app.state.glm_client = provider
        running = asyncio.create_task(analyst.AnalystSupervisor(client.app).run_once())
        try:
            await asyncio.wait_for(provider.started.wait(), timeout=2)
            response = client.delete(f"/api/v1/tasks/{client.task_id}")
            assert response.status_code == 204, response.text
        finally:
            provider.release.set()
            await asyncio.wait_for(running, timeout=2)
        assert get_row(client, Analysis, client.task_id) is None
        ledger = get_row(client, AnalystJob, job.id)
        assert ledger is not None
        assert ledger.status == "failed"
        assert ledger.task_id is None and ledger.report_id is None and ledger.message_id is None
        assert json.loads(ledger.payload_json) == {"automatic": False}
        assert ledger.request_id == job.request_id
        assert ledger.created_at == job.created_at
        assert ledger.attempts == 1
        assert all_rows(client, AnalystReport) == []
        assert all_rows(client, AnalystMessage) == []
        assert all_rows(client, AnalystConversation) == []
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["report", "message"])
@pytest.mark.parametrize("late_error", [False, True])
def test_memory_changes_preserve_inflight_session_but_revoke_chat_without_refunding_quota(job_client, report_body, kind, late_error):
    client = job_client
    client.app.state.settings = client.app.state.settings.model_copy(update={"analyst_daily_limit": 1})
    profile = client.post("/api/v1/training-profiles", json={"kind": "player", "name": "Player"})
    assert profile.status_code == 201, profile.text
    context = client.put(f"/api/v1/tasks/{client.task_id}/analyst/context", json={
        "subjects": [{"id": "player_1", "profile_id": profile.json()["id"]}],
    })
    assert context.status_code == 200, context.text
    job = request_report(client) if kind == "report" else request_chat(client)[0]

    async def run():
        provider = PausingProvider(report_body, error=GlmError("timeout", retryable=True) if late_error else None)
        client.app.state.glm_client = provider
        running = asyncio.create_task(analyst.AnalystSupervisor(client.app).run_once())
        try:
            await asyncio.wait_for(provider.started.wait(), timeout=2)
            updated = client.patch(f"/api/v1/training-profiles/{profile.json()['id']}", json={"goals": "Changed goal"})
            assert updated.status_code == 200, updated.text
            revoked = get_row(client, AnalystJob, job.id)
            if kind == "report":
                assert revoked.status == "running"
                assert revoked.payload_json == job.payload_json
                assert revoked.report_id == job.report_id
            else:
                assert revoked.status == "failed"
                assert json.loads(revoked.payload_json) == {"automatic": False}
        finally:
            provider.release.set()
            await asyncio.wait_for(running, timeout=2)
        ledger = get_row(client, AnalystJob, job.id)
        if kind == "report":
            assert ledger.status == ("queued" if late_error else "completed")
            assert get_row(client, AnalystReport, job.report_id).status == ledger.status
            assert ledger.payload_json == job.payload_json
            assert ledger.request_id == job.request_id
            assert ledger.created_at == job.created_at
            assert ledger.attempts == 1
            assert json.loads(ledger.usage_json) == ({} if late_error else USAGE)
            assert await analyst.AnalystSupervisor(client.app).run_once() is False
            return
        assert ledger.status == "failed"
        assert ledger.attempts == 1
        assert ledger.created_at == job.created_at
        assert ledger.request_id == job.request_id
        assert json.loads(ledger.payload_json) == {"automatic": False}
        assert json.loads(ledger.usage_json) == {}
        assert ledger.report_id is None
        assert all_rows(client, AnalystReport) == []
        if kind == "message":
            message = get_row(client, AnalystMessage, job.message_id)
            assert message.status == "failed"
            assert message.content == ""
            assert json.loads(message.citations_json) == []
        assert await analyst.AnalystSupervisor(client.app).run_once() is False

    asyncio.run(run())
    assert client.post(report_url(client), json={"locale": "en", "style": "roast", "regenerate": True}).status_code == 429
    conversation_id = create_conversation(client)
    assert submit(client, conversation_id, request_id="after-invalidation").status_code == 429
    assert_video_completed(client)


@pytest.mark.parametrize("kind", ["report", "message"])
@pytest.mark.parametrize("invalidation_point", ["before_load", "after_load"])
def test_invalidation_between_claim_and_load_cannot_delete_ledger_or_restart_message(job_client, kind, invalidation_point, monkeypatch):
    from app.services.training_profiles import invalidate_memory

    client = job_client
    job = request_report(client) if kind == "report" else request_chat(client)[0]
    original_load = analyst.AnalystSupervisor._load

    def invalidate_before_load(supervisor, job_id):
        loaded = original_load(supervisor, job_id) if invalidation_point == "after_load" else None
        with Session(client.app.state.engine) as session:
            claimed = session.get(AnalystJob, job_id)
            assert claimed.status == "running"
            invalidate_memory(session, client.owner_id)
            session.commit()
        return loaded if invalidation_point == "after_load" else original_load(supervisor, job_id)

    monkeypatch.setattr(analyst.AnalystSupervisor, "_load", invalidate_before_load)
    assert run_once(client) is True
    ledger = get_row(client, AnalystJob, job.id)
    assert ledger is not None, "Revoked jobs must retain the quota ledger"
    assert ledger.status == "failed"
    assert ledger.attempts == 1
    assert json.loads(ledger.payload_json) == {"automatic": False}
    assert client.app.state.glm_client.calls == []
    if kind == "message":
        message = get_row(client, AnalystMessage, job.message_id)
        assert message.status == "failed"
        assert message.content == ""
        assert json.loads(message.citations_json) == []
    assert_video_completed(client)


def test_get_report_exposes_queued_preparation_before_facts_are_available(job_client):
    client = job_client
    with Session(client.app.state.engine) as session:
        analyst.enqueue_completed(session, session.get(Analysis, client.task_id), enabled=True)
        session.commit()
    output = client.app.state.storage.analysis_root(client.task_id) / "output"
    (output / "report.json").unlink()
    response = client.get(report_url(client))
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "queued", "report": None, "error": None}
    assert client.app.state.glm_client.calls == []
    assert_video_completed(client)


def test_get_report_exposes_failed_prepare_after_validation_retries_are_exhausted(job_client, monkeypatch):
    client = job_client
    with Session(client.app.state.engine) as session:
        analyst.enqueue_completed(session, session.get(Analysis, client.task_id), enabled=True)
        session.commit()
    job = all_rows(client, AnalystJob)[0]

    def unavailable_facts(*args, **kwargs):
        raise ValueError("Invalid facts artifact")

    # Restore the real fact loader before GET to distinguish failed preparation
    # state from a GET-time artifact error.
    with monkeypatch.context() as patch:
        patch.setattr('app.services.analyst_facts.load_task_facts', unavailable_facts)
        for attempt in (1, 2, 3):
            make_due(client, job.id)
            assert run_once(client) is True
            current = get_row(client, AnalystJob, job.id)
            assert current.attempts == attempt
            assert current.status == ("failed" if attempt == 3 else "queued")
    assert all_rows(client, AnalystReport) == []
    response = client.get(report_url(client))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "failed"
    assert response.json()["error"]
    assert response.json()["report"] is None
    assert client.app.state.glm_client.calls == []
    assert_video_completed(client)


@pytest.fixture
def sqlite_transactions(job_client):
    """Observe actual SQLite transactions, not SQLAlchemy's logical autobegin."""
    engine = job_client.app.state.engine
    active = {}

    def checked_out(connection, record, proxy):
        active[id(connection)] = connection

    def checked_in(connection, record):
        active.pop(id(connection), None)

    sqlalchemy_event.listen(engine, "checkout", checked_out)
    sqlalchemy_event.listen(engine, "checkin", checked_in)
    try:
        yield lambda: [connection.in_transaction for connection in list(active.values())]
    finally:
        sqlalchemy_event.remove(engine, "checkout", checked_out)
        sqlalchemy_event.remove(engine, "checkin", checked_in)


def install_uncached_inputs(client):
    root = client.app.state.storage.analysis_root(client.task_id)
    manifest = {}
    for slot in ("cam_01", "cam_02", "cam_03", "cam_04", "enrollment_video"):
        source = root / f"{slot}.mp4"
        source.write_bytes(f"Uncached raw video bytes for {slot}".encode())
        manifest[slot] = str(source)
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, client.task_id)
        task.input_manifest_json = json.dumps(manifest)
        session.add(task)
        session.commit()
    (root / "output" / "analyst_facts.json").unlink(missing_ok=True)
    return manifest


def setup_facts_entrypoint(client, entrypoint):
    if entrypoint == "prepare":
        with Session(client.app.state.engine) as session:
            analyst.enqueue_completed(session, session.get(Analysis, client.task_id), enabled=True)
            session.commit()
        return None
    if entrypoint == "task_chat":
        return create_conversation(client)
    if entrypoint == "preset_chat":
        # A persisted preset conversation exists before the POST message request;
        # its facts loader is tested separately from preset catalog discovery.
        with Session(client.app.state.engine) as session:
            conversation = AnalystConversation(owner_id=client.owner_id, preset_id="lock-test-preset",
                                               locale="en", style="coach")
            session.add(conversation)
            session.commit()
            session.refresh(conversation)
            return conversation.id
    return None


def invoke_facts_entrypoint(client, entrypoint, conversation_id):
    if entrypoint == "prepare":
        assert run_once(client) is True
        return None
    if entrypoint == "report":
        return client.post(report_url(client), json={"locale": "en"})
    return submit(client, conversation_id)


@pytest.mark.parametrize("entrypoint", ["prepare", "report", "task_chat", "preset_chat"])
def test_facts_hashing_runs_without_sqlite_write_transaction(job_client, sqlite_transactions, entrypoint, monkeypatch):
    from types import SimpleNamespace
    from app.api.routes import analyst as analyst_routes
    from app.services import analyst_facts

    client = job_client
    conversation_id = setup_facts_entrypoint(client, entrypoint)
    manifest = install_uncached_inputs(client)
    observations = []
    if entrypoint == "preset_chat":
        output = client.app.state.storage.analysis_root(client.task_id) / "output"
        client.app.state.presets = SimpleNamespace(
            group_root=lambda preset_id: output,
            rerun_manifest=lambda preset_id: manifest,
        )
    loader_name = "load_preset_facts" if entrypoint == "preset_chat" else "load_task_facts"
    original = getattr(analyst_facts, loader_name)

    def unlocked_loader(*args, **kwargs):
        states = sqlite_transactions()
        observations.append(states)
        assert not any(states), f"Raw SQLite transaction held during {loader_name}: {states}"
        return original(*args, **kwargs)

    monkeypatch.setattr(analyst_facts, loader_name, unlocked_loader)
    monkeypatch.setattr(analyst_routes, loader_name, unlocked_loader)
    response = invoke_facts_entrypoint(client, entrypoint, conversation_id)
    assert observations, "The uncached facts loader must be exercised"
    assert not any(any(states) for states in observations), observations
    if response is not None:
        assert response.status_code == 202, response.text
    else:
        assert sorted((job.kind, job.status) for job in all_rows(client, AnalystJob)) == [
            ("prepare", "completed"),
        ] + [("report", "queued")] * 6
        assert_session_variants(client)
    assert client.app.state.glm_client.calls == []


@pytest.mark.parametrize("entrypoint", ["prepare", "report", "task_chat"])
@pytest.mark.parametrize("change,expected_status", [("deleted", 404), ("unfinished", 409)])
def test_task_is_rechecked_after_facts_loading_before_queue_writes(job_client, sqlite_transactions, entrypoint, change, expected_status, monkeypatch):
    from app.api.routes import analyst as analyst_routes
    from app.services import analyst_facts

    client = job_client
    conversation_id = setup_facts_entrypoint(client, entrypoint)
    install_uncached_inputs(client)
    original = analyst_facts.load_task_facts
    changes = []

    def change_task_after_loading(app, task):
        snapshot = original(app, task)
        assert not any(sqlite_transactions()), "A concurrent task edit cannot proceed while hashing holds SQLite"
        if not changes:
            with Session(client.app.state.engine) as writer:
                current = writer.get(Analysis, client.task_id)
                if change == "deleted":
                    writer.delete(current)
                else:
                    current.status = "queued"
                    writer.add(current)
                writer.commit()
            changes.append(change)
        return snapshot

    monkeypatch.setattr(analyst_facts, "load_task_facts", change_task_after_loading)
    monkeypatch.setattr(analyst_routes, "load_task_facts", change_task_after_loading)
    response = invoke_facts_entrypoint(client, entrypoint, conversation_id)
    assert changes == [change]
    if response is not None:
        assert response.status_code == expected_status, response.text
    else:
        assert all_rows(client, AnalystJob)[0].status == "failed"
    assert all_rows(client, AnalystReport) == []
    assert all_rows(client, AnalystMessage) == []
    assert not any(job.kind in {"report", "message"} for job in all_rows(client, AnalystJob))
    assert client.app.state.glm_client.calls == []


@pytest.mark.parametrize("completed", [False, True])
def test_invalidated_chat_request_replay_returns_original_ids_without_new_quota_use(job_client, completed):
    client = job_client
    client.app.state.settings = client.app.state.settings.model_copy(update={"analyst_daily_limit": 1})
    profile = client.post("/api/v1/training-profiles", json={"kind": "player", "name": "Player"})
    assert profile.status_code == 201, profile.text
    context = client.put(f"/api/v1/tasks/{client.task_id}/analyst/context", json={
        "subjects": [{"id": "player_1", "profile_id": profile.json()["id"]}],
    })
    assert context.status_code == 200, context.text
    job, conversation_id = request_chat(client)
    if completed:
        client.app.state.glm_client = ScriptedProvider(streams=[
            [GlmTextDelta(text="Original answer"), GlmUsage(usage=dict(USAGE))],
        ])
        assert run_once(client) is True
    calls_before = list(client.app.state.glm_client.calls)
    response = client.patch(f"/api/v1/training-profiles/{profile.json()['id']}", json={"goals": "New goal"})
    assert response.status_code == 200, response.text
    ledger = get_row(client, AnalystJob, job.id)
    assert "question" not in json.loads(ledger.payload_json)
    assert get_row(client, AnalystMessage, job.message_id).status == "failed"
    assert any(message.role == "user" and message.request_id == "chat-request"
               for message in all_rows(client, AnalystMessage))

    replay = submit(client, conversation_id)
    assert replay.status_code == 202, replay.text
    assert replay.json() == {"job_id": job.id, "message_id": job.message_id}
    assert submit(client, conversation_id, content="Different question").status_code == 409
    assert submit(client, conversation_id, request_id="fresh-request").status_code == 429
    assert len(all_rows(client, AnalystJob)) == 1
    assert len(all_rows(client, AnalystMessage)) == 2
    assert get_row(client, AnalystMessage, job.message_id).status == "failed"
    assert client.app.state.glm_client.calls == calls_before
    assert run_once(client) is False


def test_invalidated_replay_uses_question_from_the_same_conversation(job_client):
    from app.services.training_profiles import invalidate_memory

    client = job_client
    client.app.state.settings = client.app.state.settings.model_copy(update={"analyst_daily_limit": 2})
    first = create_conversation(client)
    second = create_conversation(client)
    first_result = submit(client, first, content="Review my shooting")
    second_result = submit(client, second, content="Review my footwork")
    assert first_result.status_code == second_result.status_code == 202
    with Session(client.app.state.engine) as session:
        invalidate_memory(session, client.owner_id)
        session.commit()
    first_replay = submit(client, first, content="Review my shooting")
    second_replay = submit(client, second, content="Review my footwork")
    assert first_replay.status_code == second_replay.status_code == 202
    assert first_replay.json() == first_result.json()
    assert second_replay.json() == second_result.json()
    assert submit(client, first, content="Review my footwork").status_code == 409
    assert submit(client, second, content="Review my shooting").status_code == 409
    assert len(all_rows(client, AnalystJob)) == 2
    assert len(all_rows(client, AnalystMessage)) == 4
    assert client.app.state.glm_client.calls == []


@pytest.mark.parametrize("change,expected_status", [
    ("deleted", 404),
    ("unfinished", 409),
    ("updated_at", 409),
])
def test_conversation_creation_rechecks_task_after_facts_load_without_orphans(job_client, sqlite_transactions, change, expected_status, monkeypatch):
    from app.api.routes import analyst as analyst_routes
    from app.services import analyst_facts

    client = job_client
    install_uncached_inputs(client)
    original = analyst_facts.load_task_facts
    changes = []
    transaction_states = []

    def change_task_during_facts_load(app, task):
        states = sqlite_transactions()
        transaction_states.append(states)
        assert not any(states), "Conversation facts loading must not hold a SQLite write transaction"
        snapshot = original(app, task)
        if not changes:
            # Commit from a different session so the route's previously loaded
            # task stays stale until it explicitly reloads under the write lock.
            with Session(client.app.state.engine) as writer:
                current = writer.get(Analysis, client.task_id)
                assert current.status == "completed"
                if change == "deleted":
                    writer.delete(current)
                elif change == "unfinished":
                    current.status = "queued"
                    writer.add(current)
                else:
                    current.updated_at += timedelta(seconds=1)
                    writer.add(current)
                writer.commit()
            changes.append(change)
        return snapshot

    monkeypatch.setattr(analyst_facts, "load_task_facts", change_task_during_facts_load)
    monkeypatch.setattr(analyst_routes, "load_task_facts", change_task_during_facts_load)
    response = client.post("/api/v1/analyst/conversations", json={
        "task_id": client.task_id, "locale": "en", "style": "coach",
    })
    assert changes == [change]
    assert transaction_states and not any(any(states) for states in transaction_states)
    assert response.status_code == expected_status, response.text
    assert all_rows(client, AnalystConversation) == []
    assert all_rows(client, AnalystMessage) == []
    assert all_rows(client, AnalystReport) == []
    assert all_rows(client, AnalystJob) == []
    assert client.app.state.glm_client.calls == []


def test_reconcile_backfills_tasks_completed_before_ai_enablement_once(job_client, report_body, facts):
    client = job_client
    supervisor = analyst.AnalystSupervisor(client.app)
    client.app.state.settings = client.app.state.settings.model_copy(update={"glm_api_key": SecretStr("")})
    assert supervisor.reconcile_completed() == 0
    assert all_rows(client, AnalystJob) == []
    client.app.state.settings = client.app.state.settings.model_copy(update={"glm_api_key": SecretStr(FAKE_KEY)})
    assert supervisor.reconcile_completed() == 1
    assert supervisor.reconcile_completed() == 0
    client.app.state.glm_client = ScriptedProvider(reports=[report_body])
    assert run_once(client)
    jobs = assert_session_variants(client)
    client.app.state.glm_client.reports = queued_report_bodies(client, facts, report_body)
    for job in jobs:
        assert run_once(client)
        assert get_row(client, AnalystJob, job.id).status == 'completed'
    assert run_once(client) is False
    report = client.get(report_url(client)).json()
    assert report['status'] == 'completed'
    assert report['report']['locale'] == 'zh'
    assert supervisor.reconcile_completed() == 0
    assert len(client.app.state.glm_client.calls) == 6
    assert_video_completed(client)


@pytest.mark.parametrize('failed', [False, True])
def test_reconcile_preserves_existing_manual_report_and_terminal_failures(job_client, report_body, facts, failed):
    client = job_client
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, client.task_id)
        analyst.request_report(client.app, session, task)
        session.commit()
    client.app.state.glm_client = ScriptedProvider(reports=[
        GlmError('Unavailable', retryable=False) if failed else report_body,
    ])
    assert run_once(client)
    original = all_rows(client, AnalystReport)[0]
    original_job = all_rows(client, AnalystJob)[0]
    assert original.status == original_job.status == ('failed' if failed else 'completed')
    supervisor = analyst.AnalystSupervisor(client.app)
    assert supervisor.reconcile_completed() == 1
    assert supervisor.reconcile_completed() == 0
    assert run_once(client)  # Prepare only the five absent variants.
    jobs = assert_session_variants(client)
    assert sum(job.status == 'queued' for job in jobs) == 5
    assert get_row(client, AnalystReport, original.id).model_dump() == original.model_dump()
    assert get_row(client, AnalystJob, original_job.id).model_dump() == original_job.model_dump()
    client.app.state.glm_client = ScriptedProvider(reports=queued_report_bodies(client, facts, report_body))
    for _ in range(5):
        assert run_once(client)
    assert run_once(client) is False
    assert supervisor.reconcile_completed() == 0
    assert get_row(client, AnalystReport, original.id).model_dump() == original.model_dump()
    assert get_row(client, AnalystJob, original_job.id).model_dump() == original_job.model_dump()
    assert all(get_row(client, AnalystJob, job.id).status == 'completed' for job in jobs if job.id != original_job.id)
    assert len(all_rows(client, AnalystJob)) == 7
    assert len(client.app.state.glm_client.calls) == 5


def test_reconcile_preserves_original_report_after_confirmed_memory_change(job_client, report_body, facts):
    client = job_client
    supervisor = analyst.AnalystSupervisor(client.app)
    client.app.state.glm_client = ScriptedProvider(reports=[report_body])
    assert supervisor.reconcile_completed() == 1
    assert run_once(client) and run_once(client)
    original_id = all_rows(client, AnalystReport)[0].id
    original = get_row(client, AnalystReport, original_id).model_dump(mode='json')
    original_jobs = [row.model_dump(mode='json') for row in all_rows(client, AnalystJob)]
    original_reports = [row.model_dump(mode='json') for row in all_rows(client, AnalystReport)]
    jobs = assert_session_variants(client)
    original_job = next(job for job in jobs if job.report_id == original_id)
    assert sum(job.status == 'queued' for job in jobs) == 5
    from app.services.analyst_invalidation import revoke_snapshots
    with Session(client.app.state.engine) as session:
        revoke_snapshots(session, client.owner_id, task_ids={client.task_id})
        session.commit()
    assert supervisor.reconcile_completed() == 0
    assert client.get(report_url(client)).json()['status'] == 'completed'
    assert get_row(client, AnalystReport, original_id).model_dump(mode='json') == original
    assert [row.model_dump(mode='json') for row in all_rows(client, AnalystJob)] == original_jobs
    assert [row.model_dump(mode='json') for row in all_rows(client, AnalystReport)] == original_reports
    client.app.state.glm_client.reports = queued_report_bodies(client, facts, report_body)
    for _ in range(5):
        assert run_once(client)
    assert run_once(client) is False
    assert all(job.status == 'completed' for job in all_rows(client, AnalystJob))
    assert get_row(client, AnalystReport, original_id).model_dump(mode='json') == original
    assert get_row(client, AnalystJob, original_job.id).model_dump() == original_job.model_dump()
    assert len(client.app.state.glm_client.calls) == 6
    assert supervisor.reconcile_completed() == 0
    assert len(all_rows(client, AnalystJob)) == 7
    assert len([j for j in all_rows(client, AnalystJob) if j.kind == 'prepare']) == 1


@pytest.mark.parametrize('status', ['draft', 'uploading', 'running', 'canceled', 'failed', 'expired'])
def test_reconcile_ignores_tasks_without_completed_results(job_client, status):
    with Session(job_client.app.state.engine) as session:
        task = session.get(Analysis, job_client.task_id)
        task.status = status; session.add(task); session.commit()
    assert analyst.AnalystSupervisor(job_client.app).reconcile_completed() == 0
    assert all_rows(job_client, AnalystJob) == []


def test_reconcile_does_not_keep_retrying_missing_source_files(job_client):
    client = job_client
    supervisor = analyst.AnalystSupervisor(client.app)
    (client.app.state.storage.analysis_root(client.task_id) / 'output' / 'report.json').unlink()
    assert supervisor.reconcile_completed() == 1
    assert run_once(client)
    assert all_rows(client, AnalystJob)[0].status == 'failed'
    assert supervisor.reconcile_completed() == 0
    assert client.get(report_url(client)).json()['status'] == 'failed'
    assert_video_completed(client)


def test_supervisor_start_reconciles_preexisting_completed_tasks(job_client, monkeypatch):
    async def parked(*_):
        await asyncio.Event().wait()
    monkeypatch.setattr(analyst.AnalystSupervisor, '_loop', parked)
    async def check():
        supervisor = analyst.AnalystSupervisor(job_client.app)
        await supervisor.start()
        try:
            assert len(all_rows(job_client, AnalystJob)) == 1
            assert all_rows(job_client, AnalystJob)[0].kind == 'prepare'
        finally:
            await supervisor.stop()
    asyncio.run(check())


def test_reconcile_batches_and_concurrent_scans_never_duplicate_jobs(job_client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(analyst, 'RECONCILE_BATCH_SIZE', 2)
    with Session(job_client.app.state.engine) as session:
        for _ in range(4):
            session.add(Analysis(title='Earlier session', owner_id=job_client.owner_id,
                                 status='completed', input_manifest_json='{}'))
        session.commit()
    supervisor = analyst.AnalystSupervisor(job_client.app)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: supervisor.reconcile_completed(), range(2)))
    assert sum(results) == 4
    assert supervisor.reconcile_completed() == 1
    assert supervisor.reconcile_completed() == 0
    jobs = all_rows(job_client, AnalystJob)
    assert len(jobs) == len({job.task_id for job in jobs}) == 5


def test_periodic_reconcile_finds_tasks_without_another_restart(job_client, monkeypatch):
    monkeypatch.setattr(analyst, 'RECONCILE_SECONDS', 0.01)
    async def check():
        supervisor = analyst.AnalystSupervisor(job_client.app)
        maintenance = asyncio.create_task(supervisor._reconcile_loop())
        async def found():
            while not all_rows(job_client, AnalystJob):
                await asyncio.sleep(0.005)
        try:
            await asyncio.wait_for(found(), timeout=2)
            assert all_rows(job_client, AnalystJob)[0].status == 'queued'
        finally:
            maintenance.cancel()
            with pytest.raises(asyncio.CancelledError):
                await maintenance
    asyncio.run(check())


def test_reconcile_respects_disabled_accounts(job_client):
    with Session(job_client.app.state.engine) as session:
        owner = session.get(User, job_client.owner_id)
        owner.is_active = False; session.add(owner); session.commit()
    assert analyst.AnalystSupervisor(job_client.app).reconcile_completed() == 0
    assert all_rows(job_client, AnalystJob) == []


def test_existing_report_numbers_are_formatted_on_read_without_regeneration(job_client, report_body):
    client = job_client
    client.app.state.glm_client = ScriptedProvider(reports=[report_body])
    job = request_report(client)
    assert run_once(client)
    with Session(client.app.state.engine) as session:
        row = session.get(AnalystReport, job.report_id)
        body = json.loads(row.body_json)
        body['summary'] = 'Make rate 66.6666667%'
        row.body_json = json.dumps(body)
        original = row.body_json
        session.add(row); session.commit()
    count = len(all_rows(client, AnalystJob))
    assert client.get(report_url(client), params={'locale': 'en'}).json()['report']['summary'] == 'Make rate 66.67%'
    collection = client.get(report_url(client) + 's', params={'locale': 'en'}).json()
    assert next(item for item in collection['items'] if item['style'] == 'coach' and item['subject_id'] is None)['report']['summary'] == 'Make rate 66.67%'
    assert get_row(client, AnalystReport, job.report_id).body_json == original
    assert len(all_rows(client, AnalystJob)) == count


def test_chat_rounds_split_decimal_output_but_keeps_question_and_citations(job_client, facts):
    client = job_client
    reference = facts.evidence[0].id
    client.app.state.glm_client = ScriptedProvider(streams=[[
        GlmTextDelta(text='Make rate 33.33'), GlmTextDelta(text=f'566667% [{reference}]'), GlmUsage(usage=dict(USAGE)),
    ]])
    conversation_id = create_conversation(client)
    question = 'Why is the rate 0.3333566667?'
    accepted = submit(client, conversation_id, content=question)
    assert accepted.status_code == 202
    assert run_once(client)
    messages = client.get(f'/api/v1/analyst/conversations/{conversation_id}').json()['messages']
    assert next(message for message in messages if message['role'] == 'user')['content'] == question
    answer = next(message for message in messages if message['role'] == 'assistant')
    assert answer['content'] == f'Make rate 33.34% [{reference}]'
    assert answer['citations'] == [reference]
    assert get_row(client, AnalystMessage, answer['id']).content == answer['content']
    stream = client.get(f'/api/v1/analyst/conversations/{conversation_id}/events').text
    assert 'Make rate 33.34%' in stream
    assert '33.33566667' not in stream

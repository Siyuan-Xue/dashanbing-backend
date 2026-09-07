"""Regression coverage for memory invalidation without touching unrelated work."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from fastapi import HTTPException
import pytest
from sqlmodel import Session, select

from app.admin_models import AdminAttempt, AdminLease
from app.analyst_models import (
    AnalystConversation,
    AnalystJob,
    AnalystMessage,
    AnalystReport,
    TaskSubject,
    TrainingObservation,
)
from app.models import Analysis
from app.services.analyst_facts import load_task_facts
from app.services.glm import GlmError, GlmJsonResult, GlmTextDelta, GlmUsage
from app.services.training_profiles import cleanup_analyst_task, invalidate_memory, memory_context
from test_training_profiles import api, create_profile, link, seed_analyst_work


def _seed_work(client, owner, task_id, suffix):
    """Store the same facts/memory dependency snapshot as the durable queue."""
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id) if task_id else None
        facts = load_task_facts(client.app, task) if task else None
        memory = memory_context(session, task, facts) if task else {}
        payload = {
            "automatic": False,
            "facts": facts.model_dump(mode="json") if facts else {},
            "memory": memory,
            "locale": "zh",
            "style": "coach",
            "question": "How can I improve?",
        }
        report_id, conversation_id, message_id, job_id = seed_analyst_work(
            session, owner, task_id, suffix,
        )
        conversation = session.get(AnalystConversation, conversation_id)
        conversation.comparison_id = memory.get("comparison_id")
        if task is None:
            conversation.preset_id = "demo"
        session.add(conversation)
        job = session.get(AnalystJob, job_id)
        job.payload_json = json.dumps(payload)
        job.usage_json = '{"prompt_tokens":17}'
        session.add(job)
        report_job = AnalystJob(
            owner_id=owner, task_id=task_id, report_id=report_id,
            kind="report", request_id=f"report:{suffix}", status="completed",
            payload_json=json.dumps(payload), usage_json='{"total_tokens":23}',
        )
        session.add(report_job)
        session.commit()
        return report_id, conversation_id, message_id, job_id, report_job.id


def _snapshot(client, work):
    models = (AnalystReport, AnalystConversation, AnalystMessage, AnalystJob, AnalystJob)
    with Session(client.app.state.engine) as session:
        return [
            row.model_dump(mode="json") if (row := session.get(model, row_id)) else None
            for model, row_id in zip(models, work)
        ]


def _assert_revoked(client, work, before, *, expected_comparison=None):
    after = _snapshot(client, work)
    assert after[0] is None
    assert after[1] is not None
    assert after[1]["comparison_id"] == expected_comparison
    assert after[2]["status"] == "failed"
    assert after[2]["content"] == ""
    assert json.loads(after[2]["citations_json"]) == []
    assert after[2]["revision"] > before[2]["revision"]
    assert after[3]["status"] == "failed"
    for index in (3, 4):
        assert after[index]["report_id"] is None
        assert json.loads(after[index]["payload_json"]) == {"automatic": False}
        for field in ("id", "owner_id", "request_id", "created_at", "usage_json"):
            assert after[index][field] == before[index][field]


def _assert_unchanged(client, work, before, keys):
    for key in keys:
        assert _snapshot(client, work[key]) == before[key], f"Unrelated {key} work changed"


@pytest.fixture
def scoped_work(api):
    client, add_task = api
    profile_a = create_profile(client, name="Player A")
    profile_b = create_profile(client, name="Player B")
    for task_id, profile in (("task-a", profile_a), ("task-b", profile_b)):
        add_task(task_id, dataset=task_id)
        assert link(client, task_id, profile).status_code == 200
    client.headers["x-owner"] = "2"
    profile_foreign = create_profile(client, name="Other owner")
    add_task("foreign", owner=2, dataset="foreign")
    assert link(client, "foreign", profile_foreign).status_code == 200
    client.headers["x-owner"] = "1"
    work = {
        "a": _seed_work(client, 1, "task-a", "a"),
        "b": _seed_work(client, 1, "task-b", "b"),
        "preset": _seed_work(client, 1, None, "preset"),
        "foreign": _seed_work(client, 2, "foreign", "foreign"),
    }
    return client, add_task, profile_a, profile_b, work


def test_profile_edit_invalidates_only_dependent_work(scoped_work):
    client, _, profile_a, _, work = scoped_work
    before = {key: _snapshot(client, ids) for key, ids in work.items()}
    assert json.loads(before["a"][3]["payload_json"])["memory"]["profiles"][0]["id"] == profile_a

    response = client.patch(
        f"/api/v1/training-profiles/{profile_a}", json={"goals": "New goal"},
    )
    assert response.status_code == 200, response.text

    _assert_revoked(client, work["a"], before["a"])
    _assert_unchanged(client, work, before, ("b", "preset", "foreign"))


@pytest.mark.parametrize("mutation", ["unlink", "reassign", "delete_profile"])
def test_removing_profile_dependencies_preserves_unrelated_work(scoped_work, mutation):
    client, _, profile_a, _, work = scoped_work
    replacement = create_profile(client, name="Replacement") if mutation == "reassign" else None
    before = {key: _snapshot(client, ids) for key, ids in work.items()}

    if mutation == "delete_profile":
        assert client.delete(f"/api/v1/training-profiles/{profile_a}").status_code == 204
    else:
        response = link(client, "task-a", replacement)
        assert response.status_code == 200, response.text

    _assert_revoked(client, work["a"], before["a"])
    _assert_unchanged(client, work, before, ("b", "preset", "foreign"))
    with Session(client.app.state.engine) as session:
        assert session.get(Analysis, "task-a").status == "completed"
        assert session.get(TaskSubject, ("task-a", "player_1")).profile_id == replacement


def test_noop_profile_edit_does_not_revoke_any_work(scoped_work):
    client, _, profile_a, _, work = scoped_work
    before = {key: _snapshot(client, ids) for key, ids in work.items()}
    assert client.patch(f"/api/v1/training-profiles/{profile_a}", json={"name": "Player A"}).status_code == 200
    _assert_unchanged(client, work, before, work)


@pytest.mark.parametrize("scope", ["task", "profile", "empty", "unknown", "all"])
def test_explicit_scope_and_legacy_owner_reset(scoped_work, scope):
    client, _, profile_a, _, work = scoped_work
    before = {key: _snapshot(client, ids) for key, ids in work.items()}
    kwargs = {
        "task": {"task_ids": {"task-a", "foreign"}},
        "profile": {"profile_ids": {profile_a}},
        "empty": {"task_ids": set(), "profile_ids": set(), "observation_ids": set()},
        "unknown": {"task_ids": {"missing"}, "profile_ids": {"missing"}, "observation_ids": {"missing"}},
        "all": {},
    }[scope]
    with Session(client.app.state.engine) as session:
        prepare = AnalystJob(owner_id=1, kind="prepare", task_id="task-a", payload_json='{"automatic":true}')
        session.add(prepare)
        session.commit()
        prepare_id, prepare_before = prepare.id, prepare.model_dump()
        invalidate_memory(session, 1, **kwargs)
        session.commit()
        if scope == "all":
            revoked_prepare = session.get(AnalystJob, prepare_id)
            assert revoked_prepare.status == "failed"
            assert revoked_prepare.request_id == prepare_before['request_id']
            assert json.loads(revoked_prepare.payload_json) == {"automatic": True}
        else:
            assert session.get(AnalystJob, prepare_id).model_dump() == prepare_before

    affected = ("a", "b", "preset") if scope == "all" else ("a",) if scope in {"task", "profile"} else ()
    for key in affected:
        _assert_revoked(client, work[key], before[key])
    _assert_unchanged(client, work, before, set(work) - set(affected))


@pytest.mark.parametrize("expired", [False, True])
def test_cleanup_of_unlinked_task_preserves_every_other_snapshot(scoped_work, expired):
    client, add_task, _, _, work = scoped_work
    add_task("unlinked", dataset="unlinked")
    removed = _seed_work(client, 1, "unlinked", "unlinked")
    removed_before = _snapshot(client, removed)
    before = {key: _snapshot(client, ids) for key, ids in work.items()}
    with Session(client.app.state.engine) as session:
        cleanup_analyst_task(session, "unlinked", expired=expired)
        session.delete(session.get(Analysis, "unlinked"))
        session.commit()
        # Retrying cleanup after the task row has gone must stay scoped.
        cleanup_analyst_task(session, "unlinked", expired=expired)
        session.commit()
    after = _snapshot(client, removed)
    assert after[:3] == [None, None, None]
    for index in (3, 4):
        assert after[index]["task_id"] is None
        assert after[index]["report_id"] is None
        assert after[index]["message_id"] is None
        assert json.loads(after[index]["payload_json"]) == {"automatic": False}
        for field in ("id", "request_id", "created_at", "usage_json"):
            assert after[index][field] == removed_before[index][field]
    assert after[3]["status"] == "failed"
    _assert_unchanged(client, work, before, work)


def test_retention_of_unlinked_task_preserves_live_profile_and_preset_work(scoped_work):
    from app.services.retention import RetentionService

    client, add_task, _, _, work = scoped_work
    add_task("expired", dataset="expired")
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    with Session(client.app.state.engine) as session:
        for task in session.exec(select(Analysis)).all():
            task.completed_at = now - timedelta(days=181) if task.id == "expired" else now
            session.add(task)
        session.commit()
    before = {key: _snapshot(client, ids) for key, ids in work.items()}
    deleted_paths = []
    # The real retention transaction/outbox runs; filesystem deletion is recorded.
    storage = SimpleNamespace(remove_deletion_target=lambda task_id, target: deleted_paths.append((task_id, target)))
    settings = SimpleNamespace(result_retention_days=180, raw_retention_days=30, enrollment_retention_days=7)
    RetentionService(settings, client.app.state.engine, storage).run_once(now=now)
    with Session(client.app.state.engine) as session:
        assert session.get(Analysis, "expired") is None
    assert deleted_paths == [("expired", "analysis_root")]
    _assert_unchanged(client, work, before, work)


@pytest.fixture
def history_work(scoped_work):
    client, add_task, profile_a, profile_b, work = scoped_work
    add_task("history", dataset="historical-input", day=1)
    assert link(client, "history", profile_a).status_code == 200
    with Session(client.app.state.engine) as session:
        observation_id = session.exec(select(TrainingObservation).where(TrainingObservation.source_task_id == "history")).one().id
    assert link(client, "task-a", profile_a, comparison=observation_id).status_code == 200
    # Capture new work after adding the history, as the production mutator revokes
    # the previous snapshot when confirmed training memory changes.
    work["a"] = _seed_work(client, 1, "task-a", "a-with-history")
    return client, add_task, profile_a, profile_b, work, observation_id


@pytest.mark.parametrize("dependency", ["observations", "comparison"])
def test_observation_scope_follows_stored_memory_without_current_links(history_work, dependency):
    client, _, _, _, work, observation_id = history_work
    with Session(client.app.state.engine) as session:
        for row in session.exec(select(TaskSubject).where(TaskSubject.task_id == "task-a")).all():
            session.delete(row)
        conversation = session.get(AnalystConversation, work["a"][1])
        conversation.comparison_id = None
        session.add(conversation)
        for job_id in work["a"][3:]:
            job = session.get(AnalystJob, job_id)
            payload = json.loads(job.payload_json)
            memory = payload["memory"]
            assert memory["comparison"]["id"] == observation_id
            assert observation_id in {row["id"] for row in memory["observations"]}
            # Isolate the two supported reference paths using real public history.
            if dependency == "observations":
                memory["comparison"] = None
                memory["comparison_id"] = None
                memory["comparison_scope"] = None
                memory["comparison_status"] = "disabled"
            else:
                memory["observations"] = []
            job.payload_json = json.dumps(payload)
            session.add(job)
        session.commit()
    before = {key: _snapshot(client, ids) for key, ids in work.items()}
    with Session(client.app.state.engine) as session:
        invalidate_memory(session, 1, observation_ids={observation_id})
        session.commit()
    _assert_revoked(client, work["a"], before["a"])
    _assert_unchanged(client, work, before, ("b", "preset", "foreign"))


@pytest.mark.parametrize("expired", [False, True])
def test_history_source_cleanup_revokes_dependents_and_retains_unrelated_work(history_work, expired):
    client, add_task, _, _, work, observation_id = history_work
    add_task("snapshot-only", dataset="snapshot-only")
    snapshot_only = _seed_work(client, 1, "snapshot-only", "snapshot-only")
    with Session(client.app.state.engine) as session:
        old_memory = json.loads(session.get(AnalystJob, work["a"][3]).payload_json)["memory"]
        for job_id in snapshot_only[3:]:
            job = session.get(AnalystJob, job_id)
            payload = json.loads(job.payload_json)
            payload["memory"] = old_memory
            job.payload_json = json.dumps(payload)
            session.add(job)
        session.commit()
    work["snapshot-only"] = snapshot_only
    before = {key: _snapshot(client, ids) for key, ids in work.items()}
    with Session(client.app.state.engine) as session:
        cleanup_analyst_task(session, "history", expired=expired)
        session.delete(session.get(Analysis, "history"))
        session.commit()
        observation = session.get(TrainingObservation, observation_id)
        if expired:
            assert observation is not None
            assert observation.task_id is None
            assert json.loads(observation.metrics_json)["shots"]["makes"] == 1
        else:
            assert observation is None
    for key in ("a", "snapshot-only"):
        selected = observation_id if expired and key == "a" else None
        _assert_revoked(client, work[key], before[key], expected_comparison=selected)
    _assert_unchanged(client, work, before, ("b", "preset", "foreign"))


def test_profile_note_edit_preserves_valid_explicit_conversation_comparison(history_work):
    client, _, profile_a, _, work, observation_id = history_work
    before = {key: _snapshot(client, ids) for key, ids in work.items()}
    assert before["a"][1]["comparison_id"] == observation_id

    response = client.patch(f"/api/v1/training-profiles/{profile_a}", json={"notes": "New coaching note"})
    assert response.status_code == 200, response.text

    _assert_revoked(client, work["a"], before["a"], expected_comparison=observation_id)
    _assert_unchanged(client, work, before, ("b", "preset", "foreign"))
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, "task-a")
        facts = load_task_facts(client.app, task)
        memory = memory_context(session, task, facts, comparison_id=observation_id)
        assert memory["comparison_id"] == observation_id
        assert memory["profile"]["notes"] == "New coaching note"


def test_context_unlink_clears_now_incompatible_conversation_comparison(history_work):
    client, _, _, _, work, observation_id = history_work
    before = {key: _snapshot(client, ids) for key, ids in work.items()}
    assert before["a"][1]["comparison_id"] == observation_id
    assert link(client, "task-a").status_code == 200
    _assert_revoked(client, work["a"], before["a"])
    _assert_unchanged(client, work, before, ("b", "preset", "foreign"))


@pytest.mark.parametrize("mutation", ["expire", "delete", "comparison", "unlink"])
def test_task_change_preserves_same_profile_work_without_a_reference(history_work, mutation):
    client, add_task, profile_a, _, work, observation_id = history_work
    # A rerun of the same input is linked to the same profile, but its memory
    # excludes task-a because duplicate inputs are not comparable history.
    add_task("sibling", dataset="task-a", day=2)
    assert link(client, "sibling", profile_a, comparison=observation_id).status_code == 200
    work["a"] = _seed_work(client, 1, "task-a", "a-with-sibling")
    work["sibling"] = _seed_work(client, 1, "sibling", "sibling")
    before = {key: _snapshot(client, ids) for key, ids in work.items()}
    sibling_memory = json.loads(before["sibling"][3]["payload_json"])["memory"]
    assert sibling_memory["profile"]["id"] == profile_a
    assert sibling_memory["comparison"]["task_id"] == "history"
    assert "task-a" not in {row["task_id"] for row in sibling_memory["observations"]}

    if mutation in {"expire", "delete"}:
        with Session(client.app.state.engine) as session:
            cleanup_analyst_task(session, "task-a", expired=mutation == "expire")
            session.delete(session.get(Analysis, "task-a"))
            session.commit()
        assert _snapshot(client, work["a"])[:3] == [None, None, None]
    else:
        response = link(client, "task-a", player=profile_a if mutation == "comparison" else None)
        assert response.status_code == 200, response.text
        # A task-level default change does not erase an explicit, still-valid
        # selection belonging to an existing conversation.
        selected = observation_id if mutation == "comparison" else None
        _assert_revoked(client, work["a"], before["a"], expected_comparison=selected)

    _assert_unchanged(client, work, before, ("sibling", "b", "preset", "foreign"))


def test_observation_revocation_clears_inherited_answers_but_keeps_user_history(history_work):
    client, _, _, _, work, observation_id = history_work
    with Session(client.app.state.engine) as session:
        conversation_id = work["a"][1]
        user = AnalystMessage(owner_id=1, conversation_id=conversation_id, role="user",
                              status="completed", content="Keep my original question", request_id="original")
        inherited = AnalystMessage(owner_id=1, conversation_id=conversation_id, role="assistant",
                                   status="completed", content="Answer based on earlier history", citations_json='["event-1"]')
        session.add_all([user, inherited])
        session.flush()
        job = AnalystJob(owner_id=1, kind="message", task_id="task-a", message_id=inherited.id,
                         status="completed", request_id="inherited", usage_json='{"total_tokens":9}',
                         payload_json='{"automatic":false,"memory":{}}')
        session.add(job)
        session.commit()
        user_id, user_before = user.id, user.model_dump()
        message_id, job_id = inherited.id, job.id
        job_before = job.model_dump()
        invalidate_memory(session, 1, observation_ids={observation_id})
        session.commit()
        assert session.get(AnalystMessage, user_id).model_dump() == user_before
        answer = session.get(AnalystMessage, message_id)
        assert answer.status == "failed"
        assert answer.content == ""
        assert answer.citations_json == "[]"
        ledger = session.get(AnalystJob, job_id)
        assert json.loads(ledger.payload_json) == {"automatic": False}
        for field in ("id", "request_id", "created_at", "usage_json"):
            assert getattr(ledger, field) == job_before[field]


class _WaitingProvider:
    def __init__(self, *, late_error):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.late_error = late_error
        self.report_body = {"summary": "Stale report", "comparison": {
            "text": "Comparison to the confirmed training baseline", "evidence_ids": ["event-1"],
        }}

    async def _wait(self):
        self.started.set()
        await self.release.wait()
        if self.late_error:
            raise GlmError("timeout", retryable=True)

    async def complete_json(self, messages, *, request_id):
        await self._wait()
        return GlmJsonResult(data=self.report_body, usage={"total_tokens": 99})

    async def stream(self, messages, *, request_id):
        yield GlmTextDelta(text="Persisted before invalidation ")
        await self._wait()
        yield GlmTextDelta(text="late stale answer")
        yield GlmUsage(usage={"total_tokens": 99})


@pytest.mark.parametrize("kind", ["report", "message"])
@pytest.mark.parametrize("late_error", [False, True])
@pytest.mark.parametrize("mutation", ["profile_edit", "task_delete"])
def test_scoped_inflight_revocation_cannot_republish_or_release_quota(scoped_work, tmp_path, kind, late_error, mutation):
    from app.config import AppSettings
    from app.services.admin import initialize_settings
    from app.services.analyst import AnalystSupervisor, limit_requests, _comparison_inputs, validate_comparison_report

    client, add_task, profile_a, _, work = scoped_work
    client.app.state.settings = AppSettings(
        _env_file=None, runtime_root=tmp_path / "worker-runtime",
        glm_timeout_seconds=5, analyst_daily_limit=6,
    )
    initialize_settings(client.app)
    selected_id = work["a"][4 if kind == "report" else 3]
    if kind == "report":
        add_task("history", dataset="historical-input", day=1)
    with Session(client.app.state.engine) as session:
        for job in session.exec(select(AnalystJob)).all():
            job.available_at = datetime.now(timezone.utc) + timedelta(days=1)
            session.add(job)
        selected = session.get(AnalystJob, selected_id)
        selected.status = "queued"
        selected.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        if kind == "report":
            # Queue both halves of the job/target pair so success protection
            # does not reject this deliberately in-flight report fixture.
            target = session.get(AnalystReport, selected.report_id)
            target.status = "queued"
            # A successful comparison needs a real, comparable historical
            # observation. Otherwise validation would mask the writeback race.
            previous = session.get(Analysis, "history")
            previous_facts = load_task_facts(client.app, previous)
            observation = TrainingObservation(
                owner_id=1, profile_id=profile_a, source_task_id=previous.id, task_id=previous.id,
                fingerprint=previous_facts.fingerprint, mode=previous.mode,
                occurred_at=previous.completed_at, metrics_json=previous_facts.metrics.model_dump_json(),
            )
            session.add(observation)
            session.flush()
            task = session.get(Analysis, "task-a")
            facts, memory = _comparison_inputs(session, task, load_task_facts(client.app, task), observation.id)
            payload = json.loads(selected.payload_json) | {"facts": facts.model_dump(mode="json"), "memory": memory}
            selected.payload_json = json.dumps(payload)
            target.subject_id = memory["subject_id"]
            target.comparison_id = observation.id
            session.add(target)
        session.add(selected)
        session.commit()
        with pytest.raises(HTTPException) as quota:
            limit_requests(client.app, session, 1)
        assert quota.value.status_code == 429
    before = {key: _snapshot(client, ids) for key, ids in work.items()}

    async def run():
        provider = _WaitingProvider(late_error=late_error)
        if kind == "report":
            assert validate_comparison_report(provider.report_body, payload["facts"], payload["memory"]).comparison is not None
        client.app.state.glm_client = provider
        supervisor = AnalystSupervisor(client.app)
        failures = []
        original_fail = supervisor._fail

        def record_failure(job_id, error):
            failures.append(getattr(error, "code", type(error).__name__))
            return original_fail(job_id, error)

        supervisor._fail = record_failure
        running = asyncio.create_task(supervisor.run_once())
        try:
            await asyncio.wait_for(provider.started.wait(), timeout=2)
            with Session(client.app.state.engine) as session:
                active = session.get(AnalystJob, selected_id)
                assert active.status == "running"
                assert active.attempts == 1
                attempt = session.exec(select(AdminAttempt).where(AdminAttempt.job_id == selected_id)).one()
                assert attempt.kind == "ai" and attempt.owner_id == 1
                attempt_before = attempt.model_dump()
                assert session.get(AdminLease, ("ai", selected_id)) is not None
                if kind == "message":
                    assert session.get(AnalystMessage, work["a"][2]).content == "Persisted before invalidation "
            if mutation == "profile_edit":
                response = client.patch(f"/api/v1/training-profiles/{profile_a}", json={"notes": "Updated"})
                assert response.status_code == 200, response.text
            else:
                with Session(client.app.state.engine) as session:
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                    cleanup_analyst_task(session, "task-a", expired=False)
                    session.delete(session.get(Analysis, "task-a"))
                    session.commit()
            revoked = _snapshot(client, work["a"])
            active_ledger = revoked[4 if kind == "report" else 3]
            assert active_ledger["status"] == "failed"
            assert active_ledger["attempts"] == 1
            assert active_ledger["error"] is None
            if mutation == "profile_edit":
                _assert_revoked(client, work["a"], before["a"])
            else:
                assert revoked[:3] == [None, None, None]
                for index in (3, 4):
                    assert revoked[index]["task_id"] is None
                    assert revoked[index]["report_id"] is None
                    assert revoked[index]["message_id"] is None
                    assert json.loads(revoked[index]["payload_json"]) == {"automatic": False}
            for index in (3, 4):
                for field in ("id", "owner_id", "request_id", "created_at", "usage_json"):
                    assert revoked[index][field] == before["a"][index][field]
        finally:
            provider.release.set()
            assert await asyncio.wait_for(running, timeout=2) is True

        # Both a successful late response and a retryable exception must leave
        # the revoked state intact, including the previous usage/accounting.
        assert failures == (["timeout"] if late_error else [])
        assert _snapshot(client, work["a"]) == revoked
        _assert_unchanged(client, work, before, ("b", "preset", "foreign"))
        assert await supervisor.run_once() is False
        with Session(client.app.state.engine) as session:
            assert session.exec(select(AdminAttempt).where(AdminAttempt.job_id == selected_id)).one().model_dump() == attempt_before
            assert session.get(AdminLease, ("ai", selected_id)) is None

    asyncio.run(run())
    with Session(client.app.state.engine) as session:
        with pytest.raises(HTTPException) as quota:
            limit_requests(client.app, session, 1)
        assert quota.value.status_code == 429
        assert len(session.exec(select(AnalystJob).where(AnalystJob.owner_id == 1)).all()) == 6
        task = session.get(Analysis, "task-a")
        if mutation == "task_delete":
            assert task is None
        else:
            assert task.status == "completed"

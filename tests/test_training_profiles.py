import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, select


def test_durable_models_register_seven_tables_and_prepare_jobs(tmp_path):
    from app import analyst_models as models
    from app.database import create_database_engine
    from app.models import User

    engine = create_database_engine(f"sqlite:///{tmp_path / 'models.db'}")
    SQLModel.metadata.create_all(engine)
    expected = {"training_profile", "task_subject", "training_observation", "analyst_report", "analyst_conversation", "analyst_message", "analyst_job"}
    assert expected <= set(inspect(engine).get_table_names())
    with Session(engine) as session:
        user = User(username="coach", hashed_password="x")
        session.add(user)
        session.commit()
        job = models.AnalystJob(owner_id=user.id, kind="prepare", request_id="prepare:task")
        session.add(job)
        session.commit()
        assert session.get(models.AnalystJob, job.id).status == "queued"
        assert session.get(models.AnalystJob, job.id).payload_json == "{}"


@pytest.fixture
def api(tmp_path):
    from fastapi import HTTPException
    from app.api.deps import get_current_user
    from app.api.routes.analyst_context import router as context_router
    from app.api.routes.training_profiles import router as profiles_router
    from app.database import create_database_engine
    from app.models import Analysis, User

    engine = create_database_engine(f"sqlite:///{tmp_path / 'api.db'}")
    SQLModel.metadata.create_all(engine)
    app = FastAPI()
    app.state.engine = engine
    from types import SimpleNamespace
    app.state.storage = SimpleNamespace(analysis_root=lambda task_id: tmp_path / task_id)
    with Session(engine) as session:
        session.add_all([User(id=1, username="coach", hashed_password="x"), User(id=2, username="other", hashed_password="x")])
        session.commit()

    def auth(request: Request):
        owner = request.headers.get("x-owner")
        if owner not in ("1", "2"):
            raise HTTPException(status_code=401)
        return User(id=int(owner), username="coach", hashed_password="x")

    app.dependency_overrides[get_current_user] = auth
    app.include_router(profiles_router, prefix="/api/v1")
    app.include_router(context_router, prefix="/api/v1")

    def add_task(task_id, *, owner=1, mode="full", dataset="same", day=1, actions=None):
        root = tmp_path / task_id
        output = root / "output"
        output.mkdir(parents=True)
        actions = [("raw-secret", "jump_shot")] if actions is None else actions
        clips = [{"clip_id": f"{student}:{index}", "student_id": student, "action_type": action,
                  "start_ms": index * 1000, "end_ms": (index + 1) * 1000}
                 for index, (student, action) in enumerate(actions)]
        shots = [clip for clip in clips if clip["action_type"] != "triple_threat"]
        (output / "report.json").write_text(json.dumps({
            "clips": clips,
            "shot_outcomes": [{"clip_id": clip["clip_id"], "student_id": clip["student_id"], "made": True} for clip in shots],
            "shot_stats": {"attempts": len(shots), "makes": len(shots), "misses": 0, "undetermined": 0},
        }))
        (output / "summary.json").write_text('{"student_ids":["raw-secret","raw-second"]}')
        manifest = {}
        for slot in ("cam_01", "cam_02", "cam_03", "cam_04", "enrollment_video"):
            path = root / slot
            path.write_bytes(f"{dataset}-{slot}".encode())
            manifest[slot] = str(path)
        task = Analysis(id=task_id, title="training", owner_id=owner, status="completed", mode=mode,
                        completed_at=datetime(2026, 9, day, tzinfo=timezone.utc), input_manifest_json=json.dumps(manifest))
        with Session(engine) as session:
            session.add(task)
            session.commit()
        return task_id

    with TestClient(app) as client:
        client.headers["x-owner"] = "1"
        yield client, add_task


def create_profile(client, kind="player", name="Player", **kwargs):
    response = client.post("/api/v1/training-profiles", json={"kind": kind, "name": name, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def link(client, task, player=None, team=None, comparison=None):
    return client.put(f"/api/v1/tasks/{task}/analyst/context", json={
        "subjects": [{"id": "player_1", "profile_id": player}],
        "team_profile_id": team, "comparison_id": comparison,
    })


def test_profile_crud_manual_notes_and_owner_scope(api):
    client, _ = api
    profile = create_profile(client, name="  Alex  ", goals="Manual goal", notes="Manual note")
    assert client.get("/api/v1/training-profiles").json()[0]["name"] == "Alex"
    update = client.patch(f"/api/v1/training-profiles/{profile}", json={"notes": "Revised"})
    assert update.status_code == 200
    assert update.json()["goals"] == "Manual goal"
    for method, suffix, payload in [("patch", "", {"name": "stolen"}), ("delete", "", None), ("get", "/history", None)]:
        response = client.request(method, f"/api/v1/training-profiles/{profile}{suffix}", headers={"x-owner": "2"}, json=payload)
        assert response.status_code == 404
    assert client.get("/api/v1/training-profiles", headers={"x-owner": "2"}).json() == []
    assert client.get("/api/v1/training-profiles", headers={"x-owner": ""}).status_code == 401
    assert client.delete(f"/api/v1/training-profiles/{profile}").status_code == 204
    assert client.get("/api/v1/training-profiles").json() == []


@pytest.mark.parametrize("payload", [{"kind": "other", "name": "x"}, {"kind": "player", "name": " "}, {"kind": "player", "name": "x", "owner_id": 2}])
def test_profile_rejects_invalid_or_owner_injected_values(api, payload):
    client, _ = api
    assert client.post("/api/v1/training-profiles", json=payload).status_code == 422


def test_context_identity_confirmation_is_local_to_task_and_creates_player_team_history(api):
    from app.models import Analysis
    from app.services.analyst_facts import load_task_facts
    from app.services.training_profiles import memory_context

    client, add_task = api
    player = create_profile(client, goals="Keep elbow aligned", notes="Manual only")
    team = create_profile(client, kind="team", name="Squad")
    first, other = add_task("first"), add_task("other")
    assert client.get(f"/api/v1/tasks/{first}/analyst/context").json()["subjects"][0]["profile_id"] is None
    response = link(client, first, player, team)
    assert response.status_code == 200, response.text
    assert response.json()["team_profile_id"] == team
    assert "raw-secret" not in response.text
    assert client.get(f"/api/v1/tasks/{other}/analyst/context").json()["subjects"][0]["profile_id"] is None
    history = client.get(f"/api/v1/training-profiles/{player}/history").json()
    assert len(history) == 1
    assert history[0]["metrics"]["shots"]["makes"] == 1
    assert history[0]["media_available"] is True
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, first)
        memory = memory_context(session, task, load_task_facts(client.app, task), subject_id="player_1")
        assert memory["profile"]["goals"] == "Keep elbow aligned"
        assert memory["profile"]["notes"] == "Manual only"
    assert client.get(f"/api/v1/training-profiles/{team}/history").json()[0]["metrics"]["event_count"] == 1


def test_context_rejects_other_owner_tasks_profiles_comparisons_and_invalid_subjects(api):
    client, add_task = api
    task, foreign = add_task("own"), add_task("foreign", owner=2)
    own_profile = create_profile(client)
    client.headers["x-owner"] = "2"
    other_profile = create_profile(client)
    assert link(client, foreign, other_profile).status_code == 200
    observation = client.get(f"/api/v1/training-profiles/{other_profile}/history").json()[0]["id"]
    client.headers["x-owner"] = "1"
    for method in ("get", "put"):
        response = client.request(method, f"/api/v1/tasks/{foreign}/analyst/context", json={"subjects": []} if method == "put" else None)
        assert response.status_code == 404
    assert link(client, task, other_profile).status_code == 404
    assert link(client, task, own_profile, comparison=observation).status_code == 404
    for subjects in ([{"id": "raw-secret", "profile_id": own_profile}], [{"id": "__team__", "profile_id": own_profile}],
                     [{"id": "player_1", "profile_id": own_profile}, {"id": "player_2", "profile_id": own_profile}]):
        assert client.put(f"/api/v1/tasks/{task}/analyst/context", json={"subjects": subjects}).status_code == 422
    assert link(client, task, team=own_profile).status_code == 422
    assert client.get(f"/api/v1/training-profiles/{own_profile}/history").json() == []


def test_history_deduplicates_quick_full_and_reruns_preserves_multiple_sources(api):
    from app.analyst_models import TrainingObservation

    client, add_task = api
    profile = create_profile(client)
    for task, mode, day in (("quick", "quick", 1), ("full", "full", 2), ("rerun", "full", 3)):
        add_task(task, mode=mode, day=day)
        assert link(client, task, profile).status_code == 200
    history = client.get(f"/api/v1/training-profiles/{profile}/history").json()
    assert len(history) == 1
    assert history[0]["task_id"] == "rerun"
    assert history[0]["mode"] == "full"
    with Session(client.app.state.engine) as session:
        variants = session.exec(select(TrainingObservation)).all()
        assert len(variants) == 2
        full = next(row for row in variants if row.mode == "full")
        assert set(json.loads(full.sources_json)) == {"full", "rerun"}


def test_comparisons_are_same_mode_distinct_inputs_and_selected_default_reaches_memory(api):
    from app.models import Analysis
    from app.services.analyst_facts import load_task_facts
    from app.services.training_profiles import memory_context

    client, add_task = api
    profile = create_profile(client)
    for task, mode, dataset in (("previous", "full", "old"), ("quick", "quick", "quick"), ("current", "full", "new"), ("same", "full", "new")):
        add_task(task, mode=mode, dataset=dataset)
        assert link(client, task, profile).status_code == 200
    response = client.get("/api/v1/tasks/current/analyst/context")
    assert [row["task_id"] for row in response.json()["comparisons"]] == ["previous"]
    previous_id = response.json()["comparisons"][0]["id"]
    assert link(client, "current", profile, comparison=previous_id).status_code == 200
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, "current")
        memory = memory_context(session, task, load_task_facts(client.app, task), subject_id="player_1")
        assert memory["comparison_id"] == previous_id
        assert memory["comparison"]["task_id"] == "previous"
    own_id = next(row["id"] for row in client.get(f"/api/v1/training-profiles/{profile}/history").json() if row["task_id"] == "same")
    assert link(client, "current", profile, comparison=own_id).status_code == 422


def seed_analyst_work(session, owner, task, suffix, report_kind="comparison"):
    from app.analyst_models import AnalystConversation, AnalystJob, AnalystMessage, AnalystReport

    # These fixtures exercise memory-dependent snapshots; pure session reports
    # are covered separately and survive memory-only mutations.
    report = AnalystReport(owner_id=owner, task_id=task, kind=report_kind, cache_key=f"cache-{suffix}", status="completed", body_json='{"old":"memory"}')
    conversation = AnalystConversation(owner_id=owner, task_id=task)
    session.add_all([report, conversation])
    session.flush()
    message = AnalystMessage(owner_id=owner, conversation_id=conversation.id, role="assistant", status="running", content="stale")
    session.add(message)
    session.flush()
    job = AnalystJob(owner_id=owner, task_id=task, message_id=message.id, kind="message", request_id=suffix)
    session.add(job)
    session.commit()
    return report.id, conversation.id, message.id, job.id


def test_memory_changes_invalidate_stale_snapshots_and_preserve_other_owners(api):
    from app.analyst_models import AnalystJob, AnalystMessage, AnalystReport

    client, add_task = api
    profile = create_profile(client)
    add_task("own")
    add_task("foreign", owner=2)
    assert link(client, "own", profile).status_code == 200
    with Session(client.app.state.engine) as session:
        own = seed_analyst_work(session, 1, "own", "own")
        foreign = seed_analyst_work(session, 2, "foreign", "foreign")
    assert client.patch(f"/api/v1/training-profiles/{profile}", json={"goals": "changed"}).status_code == 200
    with Session(client.app.state.engine) as session:
        assert session.get(AnalystReport, own[0]) is None
        invalidated_job = session.get(AnalystJob, own[3])
        assert invalidated_job.status == "failed"
        assert json.loads(invalidated_job.payload_json) == {"automatic": False}
        message = session.get(AnalystMessage, own[2])
        assert message.status == "failed"
        assert message.revision == 1
        assert message.content == ""
        assert session.get(AnalystReport, foreign[0]) is not None
        assert session.get(AnalystJob, foreign[3]) is not None


def test_retention_detaches_confirmed_history_deletion_removes_only_its_source_and_invalidates(api):
    from app.analyst_models import AnalystConversation, AnalystJob, AnalystMessage, AnalystReport, TaskSubject, TrainingObservation
    from app.models import Analysis
    from app.services.training_profiles import cleanup_analyst_task

    client, add_task = api
    profile = create_profile(client)
    for task, day in (("original", 1), ("rerun", 2)):
        add_task(task, day=day)
        assert link(client, task, profile).status_code == 200
    with Session(client.app.state.engine) as session:
        work = seed_analyst_work(session, 1, "rerun", "delete")
        cleanup_analyst_task(session, "rerun", expired=False)
        session.delete(session.get(Analysis, "rerun"))
        session.commit()
        for model, key in ((AnalystReport, work[0]), (AnalystConversation, work[1]), (AnalystMessage, work[2])):
            assert session.get(model, key) is None
        job = session.get(AnalystJob, work[3])
        assert job.status == "failed"
        assert job.task_id is None and job.message_id is None and job.report_id is None
        assert session.exec(select(TaskSubject).where(TaskSubject.task_id == "rerun")).all() == []
    history = client.get(f"/api/v1/training-profiles/{profile}/history").json()
    assert len(history) == 1 and history[0]["task_id"] == "original"
    with Session(client.app.state.engine) as session:
        cleanup_analyst_task(session, "original", expired=True)
        session.get(Analysis, "original").status = "expired"
        session.commit()
    history = client.get(f"/api/v1/training-profiles/{profile}/history").json()
    assert len(history) == 1
    assert history[0]["task_id"] is None and history[0]["media_available"] is False
    with Session(client.app.state.engine) as session:
        cleanup_analyst_task(session, "original", expired=False)
        session.commit()
        assert session.exec(select(TrainingObservation)).all() == []


def test_profile_delete_removes_derived_history_and_unlinks_context_without_touching_tasks(api):
    client, add_task = api
    profile = create_profile(client)
    add_task("task")
    assert link(client, "task", profile).status_code == 200
    assert client.delete(f"/api/v1/training-profiles/{profile}").status_code == 204
    context = client.get("/api/v1/tasks/task/analyst/context")
    assert context.status_code == 200
    assert context.json()["subjects"][0]["profile_id"] is None
    assert context.json()["comparisons"] == []


def test_analyst_upgrade_roundtrip_and_head_metadata_agree(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.database import create_database_engine

    monkeypatch.setenv("BASKETBALL_DATABASE_URL", f"sqlite:///{tmp_path / 'migration.db'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "20260905_0008")
    command.upgrade(config, "20260905_0009")
    command.upgrade(config, "head")
    engine = create_database_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    names = {"training_profile", "task_subject", "training_observation", "analyst_report", "analyst_conversation", "analyst_message", "analyst_job"}
    assert names <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"include_object": lambda obj, name, kind, reflected, compare: name in names if kind == "table" else True})
        assert compare_metadata(context, SQLModel.metadata) == []
    command.downgrade(config, "20260905_0008")
    assert not names & set(inspect(engine).get_table_names())
    command.upgrade(config, "head")
    assert names <= set(inspect(engine).get_table_names())


def test_quota_accounting_survives_profile_context_changes_and_task_deletion(api):
    from fastapi import HTTPException
    from types import SimpleNamespace
    from app.analyst_models import AnalystJob
    from app.services.analyst import limit_requests
    from app.services.training_profiles import cleanup_analyst_task

    client, add_task = api
    profile = create_profile(client)
    add_task("quota")
    with Session(client.app.state.engine) as session:
        jobs = [AnalystJob(owner_id=1, kind="report", task_id="quota", request_id="billable", status="completed", usage_json='{"total_tokens":17}', payload_json='{"automatic":false,"memory":{"notes":"old"}}'),
                AnalystJob(owner_id=1, kind="prepare", task_id="quota", request_id="prepare", payload_json='{"automatic":true}'),
                AnalystJob(owner_id=1, kind="message", task_id="quota", request_id="pending", status="running", payload_json='{"automatic":false,"question":"private"}')]
        session.add_all(jobs)
        session.commit()
        billable, prepare, pending = [row.id for row in jobs]
        created = session.get(AnalystJob, billable).created_at
    assert link(client, "quota", profile).status_code == 200
    assert client.patch(f"/api/v1/training-profiles/{profile}", json={"notes": "New"}).status_code == 200
    quota_app = SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(analyst_daily_limit=2)))
    with Session(client.app.state.engine) as session:
        assert session.get(AnalystJob, prepare).status == "queued"
        assert session.get(AnalystJob, pending).status == "failed"
        assert session.get(AnalystJob, billable).created_at == created
        assert session.get(AnalystJob, billable).usage_json == '{"total_tokens":17}'
        with pytest.raises(HTTPException) as error:
            limit_requests(quota_app, session, 1)
        assert error.value.status_code == 429
        cleanup_analyst_task(session, "quota", expired=False)
        session.commit()
        with pytest.raises(HTTPException) as error:
            limit_requests(quota_app, session, 1)
        assert error.value.status_code == 429
        for row in session.exec(select(AnalystJob)).all():
            assert row.task_id is None
            assert set(json.loads(row.payload_json)) == {"automatic"}
        assert session.get(AnalystJob, prepare).status == "failed"


def test_unlinking_a_rerun_removes_only_its_confirmed_source_and_clears_deleted_comparison(api):
    from app.analyst_models import AnalystJob, AnalystReport
    from app.services.training_profiles import cleanup_analyst_task

    client, add_task = api
    profile = create_profile(client, notes="Manual")
    for task, day, dataset in (("first", 1, "old"), ("repeat", 2, "old"), ("current", 3, "new")):
        add_task(task, day=day, dataset=dataset)
        assert link(client, task, profile).status_code == 200
    assert link(client, "repeat").status_code == 200
    prior = client.get("/api/v1/tasks/current/analyst/context").json()["comparisons"][0]
    assert prior["task_id"] == "first"
    assert link(client, "current", profile, comparison=prior["id"]).status_code == 200
    memory = read_memory(client, "current")
    with Session(client.app.state.engine) as session:
        other_work = seed_analyst_work(session, 1, "current", "comparison-cache")
        session.get(AnalystJob, other_work[3]).payload_json = json.dumps({"memory": memory, "automatic": False})
        session.add(AnalystJob(owner_id=1, task_id="current", kind="report", report_id=other_work[0], status="completed",
                              payload_json=json.dumps({"memory": memory, "automatic": False})))
        session.commit()
        cleanup_analyst_task(session, "first", expired=False)
        session.commit()
        assert session.get(AnalystReport, other_work[0]) is None
        assert session.get(AnalystJob, other_work[3]).status == "failed"
    context = client.get("/api/v1/tasks/current/analyst/context").json()
    assert context["comparison_id"] is None and context["comparisons"] == []
    assert client.get("/api/v1/training-profiles").json()[0]["notes"] == "Manual"


def test_invalidated_stream_and_failure_cannot_republish_or_requeue_old_memory(api):
    from app.analyst_models import AnalystJob, AnalystMessage
    from app.services.analyst import AnalystSupervisor

    client, add_task = api
    profile = create_profile(client)
    add_task("stream")
    assert link(client, "stream", profile).status_code == 200
    with Session(client.app.state.engine) as session:
        work = seed_analyst_work(session, 1, "stream", "stream-request")
        session.get(AnalystJob, work[3]).status = "running"
        session.commit()
    assert client.patch(f"/api/v1/training-profiles/{profile}", json={"notes": "corrected"}).status_code == 200
    supervisor = AnalystSupervisor(client.app)
    assert supervisor._write_message(work[3], "old response", {"facts": {"evidence": []}}, completed=True) is False
    supervisor._fail(work[3], ValueError("old failure"))
    with Session(client.app.state.engine) as session:
        assert session.get(AnalystJob, work[3]).status == "failed"
        message = session.get(AnalystMessage, work[2])
        assert message.status == "failed" and message.content == ""


@pytest.mark.parametrize("payload", [{"name": None}, {"goals": None}, {"notes": None}, {"name": " "}, {"kind": "team"}])
def test_profile_patch_invalid_values_leave_manual_fields_unchanged(api, payload):
    client, _ = api
    profile = create_profile(client, goals="keep", notes="manual")
    assert client.patch(f"/api/v1/training-profiles/{profile}", json=payload).status_code == 422
    row = client.get("/api/v1/training-profiles").json()[0]
    assert row["goals"] == "keep" and row["notes"] == "manual"


def read_memory(client, task_id, subject_id=None, comparison_id=None):
    from app.models import Analysis
    from app.services.analyst_facts import load_task_facts
    from app.services.training_profiles import memory_context

    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        return memory_context(session, task, load_task_facts(client.app, task), subject_id, comparison_id)


@pytest.mark.parametrize("kind", ["player", "team"])
def test_first_link_explicit_null_disables_comparison_despite_valid_history(api, kind):
    from app.analyst_models import TaskSubject, TrainingObservation
    from app.services.training_profiles import COMPARISON_SUBJECT, TEAM_SUBJECT

    client, add_task = api
    profile = create_profile(client, kind=kind)
    assignment = {kind: profile}
    add_task("previous", dataset="old", day=1)
    assert link(client, "previous", **assignment).status_code == 200
    previous_id = client.get(f"/api/v1/training-profiles/{profile}/history").json()[0]["id"]
    add_task("current", dataset="new", day=3)
    assert read_memory(client, "current")["comparison_status"] == "unlinked"

    response = link(client, "current", comparison=None, **assignment)
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()["comparisons"]] == [previous_id]
    assert response.json()["comparison_id"] is None
    subject_id = "player_1" if kind == "player" else TEAM_SUBJECT
    with Session(client.app.state.engine) as session:
        assert session.get(TaskSubject, ("current", subject_id)).profile_id == profile
        assert session.get(TaskSubject, ("current", COMPARISON_SUBJECT)).label == "none"
        assert session.get(TaskSubject, ("current", TEAM_SUBJECT)).selected_comparison_id is None
        observation = session.exec(select(TrainingObservation).where(
            TrainingObservation.source_task_id == "current")).one()
        assert observation.profile_id == profile

    # New history and a later link-only edit must not turn comparison back on.
    add_task("late-confirmed", dataset="late", day=2)
    assert link(client, "late-confirmed", **assignment).status_code == 200
    payload = ({"subjects": [{"id": "player_1", "profile_id": profile}]} if kind == "player"
               else {"team_profile_id": profile})
    omitted = client.put("/api/v1/tasks/current/analyst/context", json=payload)
    assert omitted.status_code == 200, omitted.text
    assert omitted.json()["comparison_id"] is None
    assert client.get("/api/v1/tasks/current/analyst/context").json()["comparison_id"] is None
    memory = read_memory(client, "current", "player_1" if kind == "player" else None)
    assert memory["profile"]["id"] == profile
    assert len(memory["observations"]) == 2
    assert memory["comparison_status"] == "disabled"
    assert memory["comparison_id"] is None
    assert memory["comparison"] is None
    assert memory["comparison_scope"] is None


@pytest.mark.parametrize("comparison_fields, preference, status", [
    ({}, "none", "disabled"),
    ({"comparison_id": None}, "none", "disabled"),
])
def test_first_link_without_history_disables_comparison_for_omission_and_null(api, comparison_fields, preference, status):
    from app.analyst_models import TaskSubject
    from app.services.training_profiles import COMPARISON_SUBJECT

    client, add_task = api
    profile = create_profile(client)
    add_task("current")
    response = client.put("/api/v1/tasks/current/analyst/context", json={
        "subjects": [{"id": "player_1", "profile_id": profile}], **comparison_fields,
    })
    assert response.status_code == 200, response.text
    assert response.json()["comparison_id"] is None
    assert response.json()["comparisons"] == []
    assert read_memory(client, "current", "player_1")["comparison_status"] == status
    with Session(client.app.state.engine) as session:
        assert session.get(TaskSubject, ("current", COMPARISON_SUBJECT)).label == preference


@pytest.mark.parametrize("preference", ["none", "auto", "explicit"])
def test_repeated_context_preserves_reports_but_changed_baseline_invalidates(api, preference):
    from app.analyst_models import AnalystConversation, AnalystJob, AnalystMessage, AnalystReport, TaskSubject, TrainingObservation
    from app.services.training_profiles import COMPARISON_SUBJECT, TEAM_SUBJECT

    client, add_task = api
    profile = create_profile(client)
    for task_id, day in (("older", 1), ("nearest", 2)):
        add_task(task_id, dataset=task_id, day=day)
        assert link(client, task_id, profile).status_code == 200
    history = {row["task_id"]: row["id"] for row in client.get(f"/api/v1/training-profiles/{profile}/history").json()}
    add_task("current", dataset="new", day=3)
    payload = {"subjects": [{"id": "player_1", "profile_id": profile}]}
    initial_id = {"none": None, "auto": history["nearest"], "explicit": history["older"]}[preference]
    if preference != "auto":
        payload["comparison_id"] = initial_id
    response = client.put("/api/v1/tasks/current/analyst/context", json=payload)
    assert response.status_code == 200, response.text
    if preference == "auto":
        # Automatic preferences exist only in legacy records, never new links.
        with Session(client.app.state.engine) as session:
            marker = session.get(TaskSubject, ("current", COMPARISON_SUBJECT))
            marker.label = "auto"
            session.add(marker)
            team = session.get(TaskSubject, ("current", TEAM_SUBJECT))
            team.selected_comparison_id = initial_id
            session.add(team)
            session.commit()
        response = client.get("/api/v1/tasks/current/analyst/context")
    assert response.json()["comparison_id"] == initial_id
    with Session(client.app.state.engine) as session:
        assert session.get(TaskSubject, ("current", COMPARISON_SUBJECT)).label == preference
        work = seed_analyst_work(session, 1, "current", "baseline")
        observation_id = session.exec(select(TrainingObservation).where(
            TrainingObservation.source_task_id == "current")).one().id
        protected = list(zip((AnalystReport, AnalystConversation, AnalystMessage, AnalystJob), work)) + [
            (TaskSubject, ("current", "player_1")), (TaskSubject, ("current", TEAM_SUBJECT)),
            (TaskSubject, ("current", COMPARISON_SUBJECT)), (TrainingObservation, observation_id),
        ]
        before = [session.get(model, key).model_dump(mode="json") for model, key in protected]

    repeated = client.put("/api/v1/tasks/current/analyst/context", json=payload)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["comparison_id"] == initial_id
    with Session(client.app.state.engine) as session:
        after = [session.get(model, key).model_dump(mode="json") if session.get(model, key) else None
                 for model, key in protected]
        assert after == before

    # Enabling comparison, opting out of auto, or switching an explicit baseline
    # must revoke a report already generated with the confirmed context.
    changed_id = None if preference == "auto" else history["nearest"]
    changed = client.put("/api/v1/tasks/current/analyst/context", json={**payload, "comparison_id": changed_id})
    assert changed.status_code == 200, changed.text
    assert changed.json()["comparison_id"] == changed_id
    memory = read_memory(client, "current", "player_1")
    assert memory["comparison_id"] == changed_id
    assert memory["comparison_status"] == ("disabled" if changed_id is None else "selected")
    with Session(client.app.state.engine) as session:
        assert session.get(AnalystReport, work[0]) is None
        assert session.get(AnalystJob, work[3]).status == "failed"
        assert json.loads(session.get(AnalystJob, work[3]).payload_json) == {"automatic": False}
        message = session.get(AnalystMessage, work[2])
        assert message.status == "failed" and message.content == ""
        assert session.get(TrainingObservation, observation_id).model_dump(mode="json") == before[-1]


def test_no_common_action_is_not_comparable_even_with_same_profile_and_mode(api):
    client, add_task = api
    profile = create_profile(client)
    add_task("previous", dataset="old", day=1, actions=[("raw-secret", "layup")])
    add_task("current", dataset="new", day=2)
    assert link(client, "previous", profile).status_code == 200
    old_id = client.get(f"/api/v1/training-profiles/{profile}/history").json()[0]["id"]
    response = client.put("/api/v1/tasks/current/analyst/context", json={"subjects": [{"id": "player_1", "profile_id": profile}]})
    assert response.status_code == 200
    assert response.json()["comparisons"] == []
    assert response.json()["comparison_id"] is None
    memory = read_memory(client, "current", "player_1")
    assert memory["comparison"] is None
    assert memory["comparison_status"] == "disabled"
    assert link(client, "current", profile, comparison=old_id).status_code == 422


def test_first_link_lists_valid_history_without_selecting_it_and_explicit_none_survives(api):
    client, add_task = api
    profile = create_profile(client)
    historical = [("older", 1, "full", [("raw-secret", "jump_shot")]),
                  ("nearest", 2, "full", [("raw-secret", "jump_shot")]),
                  ("different-action", 3, "full", [("raw-secret", "layup")]),
                  ("wrong-mode", 4, "quick", [("raw-secret", "jump_shot")]),
                  ("empty", 4, "full", []),
                  ("future", 6, "full", [("raw-secret", "jump_shot")])]
    for task, day, mode, actions in historical:
        add_task(task, dataset=task, day=day, mode=mode, actions=actions)
        assert link(client, task, profile).status_code == 200
    add_task("current", dataset="current", day=5)
    result = client.put("/api/v1/tasks/current/analyst/context", json={"subjects": [{"id": "player_1", "profile_id": profile}]})
    assert result.status_code == 200
    rows = result.json()["comparisons"]
    assert [row["task_id"] for row in rows] == ["nearest", "older"]
    assert result.json()["comparison_id"] is None
    assert read_memory(client, "current", "player_1")["comparison"] is None
    # A later explicit null is durable, rather than requesting another default.
    assert link(client, "current", profile, comparison=None).json()["comparison_id"] is None
    assert client.patch(f"/api/v1/training-profiles/{profile}", json={"notes": "Manual edit"}).status_code == 200
    add_task("late-confirmed", dataset="late", day=4)
    assert link(client, "late-confirmed", profile).status_code == 200
    memory = read_memory(client, "current", "player_1")
    assert memory["comparison"] is None
    assert memory["comparison_status"] == "disabled"
    assert client.get("/api/v1/tasks/current/analyst/context").json()["comparison_id"] is None
    older_id = rows[1]["id"]
    assert link(client, "current", profile, comparison=older_id).status_code == 200
    assert read_memory(client, "current", "player_1")["comparison"]["task_id"] == "older"
    # Omitting comparison_id during a context edit preserves that explicit choice.
    omitted = client.put("/api/v1/tasks/current/analyst/context", json={"subjects": [{"id": "player_1", "profile_id": profile}]})
    assert omitted.status_code == 200
    assert omitted.json()["comparison_id"] == older_id


def test_person_comparisons_do_not_use_another_players_actions_or_team_metrics(api):
    client, add_task = api
    player = create_profile(client)
    team = create_profile(client, kind="team")
    add_task("jump", dataset="old-jump", day=1)
    add_task("layup", dataset="old-layup", day=2, actions=[("raw-secret", "layup")])
    for task in ("jump", "layup"):
        assert link(client, task, player, team).status_code == 200
    add_task("current", dataset="new", day=3, actions=[("raw-secret", "layup"), ("raw-second", "jump_shot")])
    response = client.put("/api/v1/tasks/current/analyst/context", json={
        "subjects": [{"id": "player_1", "profile_id": player}], "team_profile_id": team,
    })
    assert response.status_code == 200
    candidates = response.json()["comparisons"]
    assert not any(row["task_id"] == "jump" and row["profile_id"] == player for row in candidates)
    assert any(row["task_id"] == "jump" and row["profile_id"] == team for row in candidates)
    selected = next(row['id'] for row in candidates if row['task_id'] == 'layup' and row['profile_id'] == player)
    memory = read_memory(client, "current", "player_1", comparison_id=selected)
    assert memory["comparison"]["task_id"] == "layup"
    assert memory["comparison"]["profile_id"] == player
    scope = memory["comparison_scope"]
    assert scope["subject_id"] == "player_1"
    assert scope["actions"] == ["layup"]
    assert scope["current_metrics"]["action_counts"]["jump_shot"] == 0
    assert scope["current_metrics"]["registered_participant_count"] == 1
    assert read_memory(client, "current", "player_2")["comparison"] is None


def test_partial_action_overlap_marks_aggregate_shot_rates_as_not_comparable(api):
    client, add_task = api
    profile = create_profile(client)
    add_task("previous", dataset="old", day=1, actions=[("raw-secret", "jump_shot"), ("raw-secret", "layup")])
    assert link(client, "previous", profile).status_code == 200
    add_task("current", dataset="new", day=2)
    assert client.put("/api/v1/tasks/current/analyst/context", json={"subjects": [{"id": "player_1", "profile_id": profile}]}).status_code == 200
    selected = client.get('/api/v1/tasks/current/analyst/context').json()['comparisons'][0]['id']
    memory = read_memory(client, "current", "player_1", comparison_id=selected)
    assert memory["comparison"] is not None
    assert memory["comparison_scope"]["actions"] == ["jump_shot"]
    assert memory["comparison_scope"]["shot_totals_comparable"] is False


def test_explicit_comparison_keeps_expired_confirmed_stats_and_skips_malformed_history(api):
    from app.analyst_models import TrainingObservation
    from app.services.training_profiles import cleanup_analyst_task

    client, add_task = api
    profile = create_profile(client)
    add_task("expired", dataset="old", day=1)
    assert link(client, "expired", profile).status_code == 200
    with Session(client.app.state.engine) as session:
        cleanup_analyst_task(session, "expired", expired=True)
        session.add(TrainingObservation(owner_id=1, profile_id=profile, mode="full", fingerprint="invalid", source_task_id="bad",
                    occurred_at=datetime(2026, 9, 2, tzinfo=timezone.utc), metrics_json="not json"))
        session.commit()
    add_task("current", dataset="new", day=3)
    response = client.put("/api/v1/tasks/current/analyst/context", json={"subjects": [{"id": "player_1", "profile_id": profile}]})
    assert response.status_code == 200
    assert response.json()['comparison_id'] is None
    assert len(response.json()['comparisons']) == 1
    memory = read_memory(client, "current", "player_1", comparison_id=response.json()['comparisons'][0]['id'])
    assert memory["comparison"] is not None
    assert memory["comparison"]["task_id"] is None
    assert memory["comparison"]["media_available"] is False
    assert memory["comparison"]["metrics"]["action_counts"]["jump_shot"] == 1


@pytest.mark.parametrize("mutation", ["reassign", "switch_subject", "delete_profile", "cleanup"])
def test_invalidation_scope_captures_old_dependencies_before_they_are_removed(api, monkeypatch, mutation):
    from app.analyst_models import TrainingObservation
    from app.services import training_profiles

    client, add_task = api
    old_profile = create_profile(client)
    new_profile = create_profile(client, name="Replacement")
    add_task("task")
    assert link(client, "task", old_profile).status_code == 200
    with Session(client.app.state.engine) as session:
        observation_id = session.exec(select(TrainingObservation)).one().id
    captured = []
    original = training_profiles.invalidate_memory

    def record_scope(session, owner_id, **scope):
        captured.append((owner_id, scope))
        original(session, owner_id, **scope)

    monkeypatch.setattr(training_profiles, "invalidate_memory", record_scope)
    if mutation == "reassign":
        assert link(client, "task", new_profile).status_code == 200
        with Session(client.app.state.engine) as session:
            new_observation_id = session.exec(select(TrainingObservation)).one().id
        assert captured[0][1]["observation_ids"] == {observation_id, new_observation_id}
        assert not captured[0][1].get("profile_ids")
    elif mutation == "switch_subject":
        response = client.put("/api/v1/tasks/task/analyst/context", json={"subjects": [{"id": "player_2", "profile_id": old_profile}]})
        assert response.status_code == 200
        assert captured[0][1]["observation_ids"] == {observation_id}
        assert not captured[0][1].get("profile_ids")
    elif mutation == "delete_profile":
        assert client.delete(f"/api/v1/training-profiles/{old_profile}").status_code == 204
        assert captured[0][1]["observation_ids"] == {observation_id}
        assert captured[0][1]["profile_ids"] == {old_profile}
    else:
        with Session(client.app.state.engine) as session:
            training_profiles.cleanup_analyst_task(session, "task", expired=False)
            session.commit()
        assert captured[0][1]["task_ids"] == {"task"}
        assert captured[0][1]["observation_ids"] == {observation_id}
        assert not captured[0][1].get("profile_ids")
    assert captured[0][0] == 1
    with Session(client.app.state.engine) as session:
        if mutation == "switch_subject":
            assert json.loads(session.get(TrainingObservation, observation_id).metrics_json)["event_count"] == 0
        else:
            assert session.get(TrainingObservation, observation_id) is None


@pytest.mark.parametrize("mutation", ["comparison", "expire", "delete", "observation_update"])
def test_same_profile_report_without_changed_source_dependency_is_preserved(api, mutation):
    from app.analyst_models import AnalystConversation, AnalystJob, AnalystMessage, AnalystReport, TrainingObservation
    from app.models import Analysis
    from app.services.training_profiles import cleanup_analyst_task

    client, add_task = api
    profile = create_profile(client)
    for task, day in (("history", 1), ("b", 2), ("a", 3)):
        add_task(task, dataset=task, day=day)
        assert link(client, task, profile).status_code == 200
    memory_b = read_memory(client, "b")
    assert all(row["task_id"] != "a" for row in memory_b["observations"])
    with Session(client.app.state.engine) as session:
        work = seed_analyst_work(session, 1, "b", "unrelated-b")
        message_job = session.get(AnalystJob, work[3])
        message_job.payload_json = json.dumps({"memory": memory_b, "automatic": False})
        report_job = AnalystJob(owner_id=1, task_id="b", kind="report", report_id=work[0], status="completed",
                                payload_json=json.dumps({"memory": memory_b, "automatic": False}))
        session.add(report_job)
        session.commit()
        protected = [(AnalystReport, work[0]), (AnalystConversation, work[1]), (AnalystMessage, work[2]),
                     (AnalystJob, work[3]), (AnalystJob, report_job.id)]
        before = [session.get(model, key).model_dump(mode="json") for model, key in protected]
        history_id = session.exec(select(TrainingObservation).where(TrainingObservation.source_task_id == "history")).one().id
    if mutation == "comparison":
        assert link(client, "a", profile, comparison=history_id).status_code == 200
    elif mutation == "observation_update":
        assert client.put("/api/v1/tasks/a/analyst/context", json={"subjects": [{"id": "player_2", "profile_id": profile}]}).status_code == 200
    else:
        with Session(client.app.state.engine) as session:
            cleanup_analyst_task(session, "a", expired=mutation == "expire")
            if mutation == "expire":
                session.get(Analysis, "a").status = "expired"
            else:
                session.delete(session.get(Analysis, "a"))
            session.commit()
    with Session(client.app.state.engine) as session:
        after = [session.get(model, key).model_dump(mode="json") if session.get(model, key) else None for model, key in protected]
        assert after == before

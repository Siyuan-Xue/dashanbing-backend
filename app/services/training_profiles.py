"""Owner-scoped confirmed memory. Mutators participate in the caller transaction."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, select

from app.analyst_models import (
    AnalystConversation, AnalystJob, AnalystMessage, AnalystReport,
    TaskSubject, TrainingObservation, TrainingProfile, utc_now,
)
from app.analyst_schemas import (
    AnalystContext, AnalystContextUpdate, AnalystFacts, AnalystMetrics,
    ContextSubject, ObservationPublic, TrainingProfilePublic,
)
from app.models import Analysis
from app.services.analyst_facts import metrics_for_subject


TEAM_SUBJECT = "__team__"
# Preference metadata shares the existing table; only actual facts subjects are
# public. Keeping a separate row distinguishes automatic defaults from opt-out.
COMPARISON_SUBJECT = "__comparison__"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def profile_or_404(session: Session, owner_id: int, profile_id: str) -> TrainingProfile:
    profile = session.exec(select(TrainingProfile).where(
        TrainingProfile.id == profile_id, TrainingProfile.owner_id == owner_id)).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Training profile not found")
    return profile


def invalidate_memory(session: Session, owner_id: int, *, task_ids: set[str] | None = None,
                      profile_ids: set[str] | None = None, observation_ids: set[str] | None = None) -> None:
    """Revoke dependent snapshots, preserving unrelated reports and quota usage."""
    from app.services.analyst_invalidation import revoke_snapshots
    revoke_snapshots(session, owner_id, task_ids=task_ids, profile_ids=profile_ids, observation_ids=observation_ids)


def _scrub_job(session: Session, job: AnalystJob, *, detach: bool = False) -> None:
    """Retain immutable quota/accounting fields while revoking stale work."""
    try:
        automatic = bool(json.loads(job.payload_json).get("automatic"))
    except (TypeError, ValueError, AttributeError):
        automatic = job.kind == "prepare"
    if job.status in {"queued", "running"}:
        job.status = "failed"
    job.payload_json = _json({"automatic": automatic})
    job.error = None
    job.report_id = None
    if detach:
        job.task_id = None
        job.message_id = None
    job.updated_at = utc_now()
    session.add(job)


def _sources(row: TrainingObservation) -> dict:
    try:
        sources = json.loads(row.sources_json)
    except (TypeError, ValueError):
        sources = {}
    if isinstance(sources, dict) and sources:
        return sources
    # Preserve provenance for records created by older/internal callers.
    metrics = _observation_metrics(row)
    return {row.source_task_id: {
        "task_id": row.task_id, "subject_id": None,
        "occurred_at": _aware(row.occurred_at).isoformat(),
        "metrics": metrics.model_dump(mode="json") if metrics else {},
    }}


def _refresh_observation(session: Session, row: TrainingObservation, sources: dict) -> None:
    if not sources:
        for assignment in session.exec(select(TaskSubject).where(TaskSubject.selected_comparison_id == row.id)).all():
            assignment.selected_comparison_id = None
            session.add(assignment)
        session.flush()
        session.delete(row)
        session.flush()
        return
    latest_id, latest = max(sources.items(), key=lambda item: (
        item[1]["occurred_at"], item[1].get("confirmed_at", ""), item[0]))
    row.source_task_id = latest_id
    row.task_id = latest.get("task_id")
    row.occurred_at = datetime.fromisoformat(latest["occurred_at"])
    row.metrics_json = _json(latest["metrics"])
    row.sources_json = _json(sources)
    session.add(row)
    session.flush()


def _task_mappings(session: Session, task: Analysis) -> list[TaskSubject]:
    return list(session.exec(select(TaskSubject).where(TaskSubject.owner_id == task.owner_id, TaskSubject.task_id == task.id)).all())


def _profile_ids(session: Session, task: Analysis, facts: AnalystFacts, subject_id: str | None = None) -> set[str]:
    if subject_id is not None and subject_id not in {subject.id for subject in facts.subjects}:
        raise HTTPException(status_code=422, detail="Unknown subject")
    valid = {subject.id for subject in facts.subjects} | {TEAM_SUBJECT}
    return {row.profile_id for row in _task_mappings(session, task)
            if row.profile_id and row.subject_id in valid and (subject_id is None or row.subject_id == subject_id)}


def observation_public(session: Session, row: TrainingObservation) -> ObservationPublic:
    task = session.get(Analysis, row.task_id) if row.task_id else None
    available = task is not None and task.owner_id == row.owner_id and task.status == "completed"
    return ObservationPublic(
        id=row.id, profile_id=row.profile_id, task_id=row.task_id if available else None,
        occurred_at=row.occurred_at, mode=row.mode, metrics=AnalystMetrics.model_validate_json(row.metrics_json),
        media_available=available,
    )


def _dedupe_history(rows: list[TrainingObservation]) -> list[TrainingObservation]:
    selected = {}
    for row in rows:
        key = (row.profile_id, row.fingerprint)
        rank = (row.mode == "full", _aware(row.occurred_at), row.source_task_id)
        previous = selected.get(key)
        if previous is None or rank > (previous.mode == "full", _aware(previous.occurred_at), previous.source_task_id):
            selected[key] = row
    return sorted(selected.values(), key=lambda row: (_aware(row.occurred_at), row.id), reverse=True)


def profile_history(session: Session, owner_id: int, profile_id: str) -> list[ObservationPublic]:
    profile_or_404(session, owner_id, profile_id)
    rows = list(session.exec(select(TrainingObservation).where(
        TrainingObservation.owner_id == owner_id, TrainingObservation.profile_id == profile_id)).all())
    return [observation_public(session, row) for row in _dedupe_history(rows)]


def comparable_observations(session: Session, task: Analysis, facts: AnalystFacts, subject_id: str | None = None) -> list[ObservationPublic]:
    _profile_ids(session, task, facts, subject_id)  # Validate a supplied subject.
    links = {row.subject_id: row.profile_id for row in _task_mappings(session, task)}
    current = _metrics_for_links(facts, links, subject_id)
    if not current:
        return []
    rows = list(session.exec(select(TrainingObservation).where(
        TrainingObservation.owner_id == task.owner_id,
        TrainingObservation.profile_id.in_(current), TrainingObservation.mode == task.mode,
        TrainingObservation.fingerprint != facts.fingerprint)).all())
    rows = [row for row in rows if _is_comparable(session, row, task, facts, current[row.profile_id][1])]
    return [observation_public(session, row) for row in _dedupe_history(rows)]


def _observation_metrics(row: TrainingObservation) -> AnalystMetrics | None:
    try:
        return AnalystMetrics.model_validate_json(row.metrics_json)
    except (TypeError, ValueError):
        return None


def _actions(metrics: AnalystMetrics) -> set[str]:
    counts = metrics.action_counts.model_dump()
    if metrics.event_count <= 0 or any(value < 0 for value in counts.values()):
        return set()
    return {action for action, count in counts.items() if count > 0}


def _metrics_for_links(facts: AnalystFacts, links: dict, subject_id: str | None = None) -> dict[str, tuple[str | None, AnalystMetrics]]:
    current = {}
    for subject in facts.subjects:
        profile_id = links.get(subject.id)
        if profile_id and (subject_id is None or subject_id == subject.id):
            current[profile_id] = (subject.id, metrics_for_subject(facts, subject.id))
    if subject_id is None and links.get(TEAM_SUBJECT):
        current[links[TEAM_SUBJECT]] = (None, facts.metrics)
    return current


def _is_comparable(session: Session, row: TrainingObservation, task: Analysis, facts: AnalystFacts, current: AnalystMetrics) -> bool:
    previous = _observation_metrics(row)
    if (previous is None or row.owner_id != task.owner_id or row.mode != task.mode
            or row.fingerprint == facts.fingerprint or task.id in _sources(row)
            or _aware(row.occurred_at) > _aware(task.completed_at or task.created_at)
            or not (_actions(current) & _actions(previous))):
        return False
    source = session.get(Analysis, row.task_id) if row.task_id else None
    # Detached confirmed observations survive natural expiry. A still-attached
    # failed/canceled source is not a valid completed training baseline.
    return row.task_id is None or (source is not None and source.owner_id == task.owner_id and source.status in {"completed", "expired"})


def _comparison_preference(session: Session, task: Analysis) -> tuple[str, str | None]:
    mappings = {row.subject_id: row for row in _task_mappings(session, task)}
    team, preference = mappings.get(TEAM_SUBJECT), mappings.get(COMPARISON_SUBJECT)
    selected = team.selected_comparison_id if team else None
    # Existing null selections predate automatic defaults; preserve them.
    mode = preference.label if preference and preference.label in {"auto", "explicit", "none"} else ("explicit" if selected else "none")
    return mode, selected


def validate_comparison(session: Session, task: Analysis, facts: AnalystFacts,
                        comparison_id: str | None = None, subject_id: str | None = None) -> ObservationPublic | None:
    candidates = comparable_observations(session, task, facts, subject_id)
    if comparison_id is None:
        preference, selected = _comparison_preference(session, task)
        if preference == "auto":
            return candidates[0] if candidates else None
        if preference == "none":
            return None
        # A stored global choice may not apply to a narrower player selection.
        # Do not substitute another person's baseline or override that choice.
        return next((item for item in candidates if item.id == selected), None)
    row = session.exec(select(TrainingObservation).where(
        TrainingObservation.id == comparison_id, TrainingObservation.owner_id == task.owner_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Comparison not found")
    result = next((item for item in candidates if item.id == comparison_id), None)
    if result is None:
        raise HTTPException(status_code=422, detail="Comparison requires prior valid training for the linked profile, same mode and a shared action")
    return result


def memory_context(session: Session, task: Analysis, facts: AnalystFacts,
                   subject_id: str | None = None, comparison_id: str | None = None) -> dict:
    """Read confirmed goals/notes and comparable history without inferring identity."""
    profile_ids = _profile_ids(session, task, facts, subject_id)
    profiles = [TrainingProfilePublic.model_validate(profile_or_404(session, task.owner_id, profile_id)).model_dump(mode="json")
                for profile_id in sorted(profile_ids)]
    comparison = validate_comparison(session, task, facts, comparison_id, subject_id)
    observations = comparable_observations(session, task, facts, subject_id)
    team = session.get(TaskSubject, (task.id, TEAM_SUBJECT))
    primary_id = team.profile_id if team and subject_id is None else None
    primary = next((profile for profile in profiles if profile["id"] == primary_id), None)
    if primary is None and len(profiles) == 1:
        primary = profiles[0]
    preference, _ = _comparison_preference(session, task)
    comparison_status = ("selected" if comparison else "unlinked" if not profiles else
                         "disabled" if preference == "none" else "no_comparable_history")
    scope = None
    if comparison:
        links = {row.subject_id: row.profile_id for row in _task_mappings(session, task)}
        compared_subject, current = _metrics_for_links(facts, links, subject_id)[comparison.profile_id]
        current_actions, previous_actions = _actions(current), _actions(comparison.metrics)
        scope = {"profile_id": comparison.profile_id, "subject_id": compared_subject,
                 "actions": sorted(current_actions & previous_actions),
                 "current_metrics": current.model_dump(mode="json"),
                 "shot_totals_comparable": current_actions == previous_actions}
    return {"subject_id": subject_id, "profile": primary, "profiles": profiles,
            "comparison_id": comparison.id if comparison else None,
            "comparison": comparison.model_dump(mode="json") if comparison else None,
            "comparison_status": comparison_status, "comparison_scope": scope,
            "observations": [row.model_dump(mode="json") for row in observations],
            "subjects": [{"id": row.subject_id, "profile_id": row.profile_id} for row in sorted(_task_mappings(session, task), key=lambda row: row.subject_id)
                         if row.subject_id != TEAM_SUBJECT and row.profile_id]}


def task_context(session: Session, task: Analysis, facts: AnalystFacts) -> AnalystContext:
    assignments = {row.subject_id: row for row in _task_mappings(session, task)}
    team = assignments.get(TEAM_SUBJECT)
    comparisons = comparable_observations(session, task, facts)
    selected = validate_comparison(session, task, facts)
    return AnalystContext(task_id=task.id, facts=facts,
        subjects=[ContextSubject(id=subject.id, label=subject.label,
                  profile_id=assignments[subject.id].profile_id if subject.id in assignments else None) for subject in facts.subjects],
        team_profile_id=team.profile_id if team else None,
        comparison_id=selected.id if selected else None, comparisons=comparisons)


def update_task_context(session: Session, task: Analysis, facts: AnalystFacts, update: AnalystContextUpdate) -> AnalystContext:
    """Replace this task's manual links and record only explicitly confirmed metrics."""
    subjects = {subject.id: subject for subject in facts.subjects}
    requested = {item.id: item.profile_id for item in update.subjects}
    if len(requested) != len(update.subjects) or set(requested) - subjects.keys():
        raise HTTPException(status_code=422, detail="Unknown or duplicate subject")
    assigned = [profile for profile in requested.values() if profile]
    if len(assigned) != len(set(assigned)):
        raise HTTPException(status_code=422, detail="Each player profile can link to one subject per task")
    desired = {subject_id: requested.get(subject_id) for subject_id in subjects}
    desired[TEAM_SUBJECT] = update.team_profile_id
    for subject_id, profile_id in desired.items():
        if profile_id:
            profile = profile_or_404(session, task.owner_id, profile_id)
            if profile.kind != ("team" if subject_id == TEAM_SUBJECT else "player"):
                raise HTTPException(status_code=422, detail="Profile kind does not match the subject")
    old = {row.subject_id: row for row in _task_mappings(session, task)}
    affected_observations: set[str] = set()
    old_mode, old_selected = _comparison_preference(session, task)
    first_link = (COMPARISON_SUBJECT not in old and not any(row.profile_id for row in old.values())
                  and any(desired.values()))
    if update.comparison_id:
        preference, selected = "explicit", update.comparison_id
    elif first_link:
        preference, selected = "auto", None
    elif "comparison_id" in update.model_fields_set:
        preference, selected = "none", None
    else:
        preference, selected = old_mode, old_selected
    # Resolve foreign/incompatible explicit IDs before writing anything.
    if selected and preference == "explicit":
        row = session.exec(select(TrainingObservation).where(TrainingObservation.id == selected, TrainingObservation.owner_id == task.owner_id)).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Comparison not found")
        current = _metrics_for_links(facts, desired).get(row.profile_id)
        if current is None or not _is_comparable(session, row, task, facts, current[1]):
            raise HTTPException(status_code=422, detail="Comparison is not compatible with these links")
    changed = any(old.get(key) is None and value is not None or old.get(key) is not None and old[key].profile_id != value for key, value in desired.items())
    changed = changed or old_selected != selected or old_mode != preference
    for subject_id, profile_id in desired.items():
        row = old.get(subject_id) or TaskSubject(task_id=task.id, subject_id=subject_id, owner_id=task.owner_id)
        row.profile_id = profile_id
        row.label = subjects[subject_id].label if subject_id != TEAM_SUBJECT else "团队"
        row.selected_comparison_id = selected if subject_id == TEAM_SUBJECT else None
        session.add(row)
    if first_link or COMPARISON_SUBJECT in old or preference == "explicit":
        marker = old.get(COMPARISON_SUBJECT) or TaskSubject(task_id=task.id, subject_id=COMPARISON_SUBJECT, owner_id=task.owner_id)
        marker.label = preference
        session.add(marker)
    session.flush()
    desired_profiles = {value: key for key, value in desired.items() if value}
    for row in session.exec(select(TrainingObservation).where(TrainingObservation.owner_id == task.owner_id)).all():
        sources = _sources(row)
        if task.id in sources and (row.profile_id not in desired_profiles or row.fingerprint != facts.fingerprint or row.mode != task.mode):
            affected_observations.add(row.id)
            del sources[task.id]
            _refresh_observation(session, row, sources)
            changed = True
    for profile_id, subject_id in desired_profiles.items():
        row = session.exec(select(TrainingObservation).where(
            TrainingObservation.owner_id == task.owner_id, TrainingObservation.profile_id == profile_id,
            TrainingObservation.fingerprint == facts.fingerprint, TrainingObservation.mode == task.mode)).first()
        metrics = facts.metrics if subject_id == TEAM_SUBJECT else metrics_for_subject(facts, subject_id)
        source = {"task_id": task.id, "subject_id": subject_id,
                  "occurred_at": _aware(task.completed_at or task.created_at).isoformat(), "metrics": metrics.model_dump(mode="json")}
        if row is None:
            row = TrainingObservation(owner_id=task.owner_id, profile_id=profile_id, source_task_id=task.id,
                                      fingerprint=facts.fingerprint, mode=task.mode)
            sources = {}
        else:
            sources = _sources(row)
        previous = sources.get(task.id, {})
        if {key: value for key, value in previous.items() if key != "confirmed_at"} != source:
            affected_observations.add(row.id)
            source["confirmed_at"] = utc_now().isoformat()
            sources[task.id] = source
            _refresh_observation(session, row, sources)
            changed = True
    if changed:
        invalidate_memory(session, task.owner_id, task_ids={task.id}, observation_ids=affected_observations)
    if preference == "auto":
        automatic = validate_comparison(session, task, facts)
        team = session.get(TaskSubject, (task.id, TEAM_SUBJECT))
        team.selected_comparison_id = automatic.id if automatic else None
        session.add(team)
        session.flush()
    return task_context(session, task, facts)


def delete_profile(session: Session, owner_id: int, profile_id: str) -> None:
    profile = profile_or_404(session, owner_id, profile_id)
    observations = list(session.exec(select(TrainingObservation).where(
        TrainingObservation.owner_id == owner_id, TrainingObservation.profile_id == profile_id)).all())
    observation_ids = {row.id for row in observations}
    for row in observations:
        _refresh_observation(session, row, {})
    for row in session.exec(select(TaskSubject).where(TaskSubject.owner_id == owner_id, TaskSubject.profile_id == profile_id)).all():
        row.profile_id = None
        session.add(row)
    session.flush()
    session.delete(profile)
    invalidate_memory(session, owner_id, profile_ids={profile_id}, observation_ids=observation_ids)


def cleanup_analyst_task(session: Session, task_id: str, expired: bool) -> None:
    """Idempotent cleanup inside the caller's task-deletion/retention transaction.

    Expiry retains confirmed metrics and source provenance with no media link.
    Explicit deletion removes that source; another rerun's contribution survives.
    """
    task = session.get(Analysis, task_id)
    owners = {task.owner_id} if task else set()
    affected_observations: set[str] = set()
    for row in session.exec(select(TrainingObservation)).all():
        sources = _sources(row)
        if task_id not in sources:
            continue
        owners.add(row.owner_id)
        affected_observations.add(row.id)
        if expired:
            sources[task_id]["task_id"] = None
        else:
            del sources[task_id]
        _refresh_observation(session, row, sources)
    conversations = list(session.exec(select(AnalystConversation).where(AnalystConversation.task_id == task_id)).all())
    conversation_ids = {row.id for row in conversations}
    for row in session.exec(select(AnalystMessage)).all():
        if row.conversation_id in conversation_ids:
            session.delete(row)
    session.flush()
    for row in conversations:
        owners.add(row.owner_id)
        session.delete(row)
    for job in session.exec(select(AnalystJob).where(AnalystJob.task_id == task_id)).all():
        owners.add(job.owner_id)
        _scrub_job(session, job, detach=True)
    for model in (AnalystReport, TaskSubject):
        for row in session.exec(select(model).where(model.task_id == task_id)).all():
            owners.add(row.owner_id)
            session.delete(row)
    session.flush()
    for owner_id in owners:
        invalidate_memory(session, owner_id, task_ids={task_id}, observation_ids=affected_observations)

"""Complete report sets, with independent full-session and personal variants."""
import json

from fastapi import HTTPException

from app.analyst_reports import ReportVariant, ReportsCollection, ReportState
from app.analyst_schemas import AnalystFacts
from app.services.analyst_facts import metrics_for_subject

STYLES = ("coach", "roast")
COLLECTION_VERSION = 1


def scoped_facts(facts: AnalystFacts, subject_id: str | None):
    if subject_id is None:
        return facts
    subjects = [subject for subject in facts.subjects if subject.id == subject_id]
    if not subjects:
        raise HTTPException(422, "球员不属于当前训练")
    evidence = [item for item in facts.evidence if item.subject_id == subject_id]
    return facts.model_copy(update={
        "subjects": subjects, "metrics": metrics_for_subject(facts, subject_id), "evidence": evidence,
        "pose_available": any(bool(item.angles) for item in evidence),
    })


def variants(facts):
    for subject_id in [None, *(subject.id for subject in facts.subjects)]:
        for style in STYLES:
            yield subject_id, style


def current_reports(app, session, task, locale="zh", *, facts=None):
    from app.services.analyst import _session_report, configured, report_state, current_report, preparation_state
    from app.services.analyst_facts import load_task_facts
    initial = None
    if task.status != "completed" or not configured(app):
        initial = ReportState(status="disabled" if not configured(app) else "waiting")
        facts = AnalystFacts()
    elif facts is None:
        try:
            facts = load_task_facts(app, task)
        except (FileNotFoundError, ValueError):
            initial = current_report(app, session, task, locale)
            facts = AnalystFacts()
    items = []
    preparing = preparation_state(session, task, locale)
    for subject_id, style in variants(facts):
        row = None if initial else _session_report(app, session, task, scoped_facts(facts, subject_id), locale, style, subject_id)
        state = initial or (report_state(row) if row else preparing or report_state(None))
        items.append(ReportVariant(**state.model_dump(), subject_id=subject_id, locale=locale, style=style))
    return ReportsCollection(items=items, facts=facts.model_dump(), subjects=[s.model_dump() for s in facts.subjects])


def request_reports(app, session, task, locale="zh", *, automatic=False, facts=None):
    from app.services.analyst import _session_report, request_report, require_complete, require_configured
    from app.services.analyst_facts import load_task_facts
    require_complete(task)
    require_configured(app)
    facts = load_task_facts(app, task) if facts is None else facts
    # The task's initial set is already covered by its task quota, including a
    # page opened before the periodic automatic backfill has queued preparation.
    charged = automatic or locale == task.analyst_locale
    for subject_id, style in variants(facts):
        # Collection refresh ensures absent variants only. Failed work has an
        # explicit per-report retry, never an unbounded backfill/reload loop.
        if _session_report(app, session, task, scoped_facts(facts, subject_id), locale, style, subject_id) is None:
            request_report(app, session, task, facts=facts, locale=locale, style=style,
                           subject_id=subject_id, automatic=charged)
            charged = True
    return current_reports(app, session, task, locale, facts=facts)


def preset_report_path(settings, preset_id, locale, style, subject_id=None):
    # Callers validate both preset and subject against the loaded facts first.
    suffix = f"-{subject_id}" if subject_id else ""
    return settings.runtime_root / "analyst-presets" / preset_id / f"{locale}-{style}{suffix}.json"


def saved_preset_report(app, preset_id, facts, locale, style, subject_id=None):
    from app.services.analyst import configured, digest, validate_report
    from app.analyst_reports import ReportPublic
    scoped = scoped_facts(facts, subject_id)
    state = ReportState(status="waiting" if configured(app) else "disabled")
    path = preset_report_path(app.state.settings, preset_id, locale, style, subject_id)
    if not path.is_file():
        return state
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        value = saved["report"]
        if (saved.get("verified") is not True or saved["facts_hash"] != digest(scoped.model_dump())
                or value["model"] != "glm-5.3" or value["locale"] != locale or value["style"] != style
                or saved.get("subject_id") != subject_id):
            return state
        public = ReportPublic.model_validate(value)
        validate_report(public.model_dump(include={"summary", "highlights", "players", "comparison", "suggestions"}), scoped.model_dump(), {})
        return ReportState(status="completed", report=public)
    except (KeyError, ValueError, TypeError):
        return state


def preset_reports(app, preset_id, locale="zh"):
    from app.services.analyst import digest
    from app.services.analyst_facts import load_preset_facts
    try:
        facts = load_preset_facts(app, preset_id)
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, "Preset not found") from None
    items = [ReportVariant(**saved_preset_report(app, preset_id, facts, locale, style, subject_id).model_dump(),
                           subject_id=subject_id, locale=locale, style=style) for subject_id, style in variants(facts)]
    return ReportsCollection(items=items, facts=facts.model_dump(), subjects=[s.model_dump() for s in facts.subjects],
                             provenance={"provider": "glm", "verified": all(i.status == "completed" for i in items), "facts_hash": digest(facts.model_dump())})

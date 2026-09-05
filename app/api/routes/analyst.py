import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_session
from app.models import User
from app.analyst_models import AnalystConversation
from app.analyst_reports import ComparisonRequest, ComparisonReportState, ComparisonReports, ConversationCreate, ConversationPublic, Locale, MessageAccepted, MessageCreate, ReportRequest, ReportState, Style
from app.services.analyst import (
    configured, conversation_messages, current_report, current_comparisons, digest, facts_and_memory,
    message_public, owned_conversation, owned_task, pack, request_report, request_comparison,
    require_complete, require_configured, replay_message, submit_message,
)
from app.services.analyst_facts import load_task_facts, load_preset_facts

router = APIRouter(tags=["AI analyst"])


@router.get('/tasks/{task_id}/analyst/report', response_model=ReportState)
def get_report(task_id: str, request: Request, locale: Locale = 'zh', style: Style = 'coach', session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    task = owned_task(session, task_id, user.id)
    return current_report(request.app, session, task, locale, style)


@router.post('/tasks/{task_id}/analyst/report', response_model=ReportState, status_code=202)
def generate_report(task_id: str, payload: ReportRequest, request: Request, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    owner_id = user.id
    task = owned_task(session, task_id, owner_id)
    require_complete(task)
    require_configured(request.app)
    version = task.updated_at
    facts = load_task_facts(request.app, task)
    session.rollback()
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    task = owned_task(session, task_id, owner_id)
    if task.updated_at != version:
        raise HTTPException(409, '任务已变化，请重新读取结果')
    result = request_report(request.app, session, task, facts=facts, **payload.model_dump())
    session.commit()
    return result


@router.get('/tasks/{task_id}/analyst/comparisons', response_model=ComparisonReports)
def get_comparisons(task_id: str, request: Request, locale: Locale = 'zh', style: Style = 'coach',
                    session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    task = owned_task(session, task_id, user.id)
    return current_comparisons(request.app, session, task, locale, style)


@router.post('/tasks/{task_id}/analyst/comparisons', response_model=ComparisonReportState, status_code=202)
def generate_comparison(task_id: str, payload: ComparisonRequest, request: Request,
                        session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    owner_id = user.id
    task = owned_task(session, task_id, owner_id)
    require_complete(task)
    require_configured(request.app)
    version = task.updated_at
    facts = load_task_facts(request.app, task)
    session.rollback()
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    task = owned_task(session, task_id, owner_id)
    require_complete(task)
    if task.updated_at != version:
        raise HTTPException(409, '任务已变化，请重新读取结果')
    result = request_comparison(request.app, session, task, facts=facts, **payload.model_dump())
    session.commit()
    return result


class PresetReportState(ReportState):
    facts: dict = Field(default_factory=dict)
    subjects: list[dict] = Field(default_factory=list)
    provenance: dict | None = None


@router.get('/presets/{preset_id}/analyst/report', response_model=PresetReportState)
def preset_report(preset_id: str, request: Request, locale: Locale = 'zh', style: Style = 'coach', session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    try:
        facts, _ = facts_and_memory(request.app, session, preset_id=preset_id)
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, 'Preset not found') from None
    state = {'status': 'waiting' if configured(request.app) else 'disabled', 'facts': facts.model_dump(), 'subjects': [s.model_dump() | {'profile_id': None} for s in facts.subjects]}
    path = request.app.state.settings.runtime_root / 'analyst-presets' / preset_id / f'{locale}-{style}.json'
    if path.is_file():
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            if saved['facts_hash'] == digest(facts.model_dump()) and saved.get('verified') and saved['report']['model'] == 'glm-5.3':
                return PresetReportState(**(state | {'status':'completed','report':saved['report'],'provenance':{'provider':'glm','verified':True,'facts_hash':saved['facts_hash']}}))
        except (KeyError, ValueError):
            pass
    return PresetReportState(**state)


@router.post('/analyst/conversations', response_model=ConversationPublic, status_code=201)
def create_conversation(payload: ConversationCreate, request: Request, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    owner_id = user.id
    task = owned_task(session, payload.task_id, owner_id) if payload.task_id else None
    if task:
        require_complete(task)
    version = task.updated_at if task else None
    try:
        facts, _ = facts_and_memory(request.app, session, task=task, preset_id=payload.preset_id, subject_id=payload.subject_id, comparison_id=payload.comparison_id)
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, 'Preset not found') from None
    if payload.subject_id and payload.subject_id not in {s.id for s in facts.subjects}:
        raise HTTPException(422, '球员不属于当前训练')
    if payload.preset_id and payload.comparison_id:
        raise HTTPException(422, '示例不关联个人训练档案')
    session.rollback()
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    if payload.task_id:
        task = owned_task(session, payload.task_id, owner_id)
        require_complete(task)
        if task.updated_at != version:
            raise HTTPException(409, '任务已变化，请重新读取结果')
        facts_and_memory(request.app, session, task=task, facts=facts, subject_id=payload.subject_id, comparison_id=payload.comparison_id)
    row = AnalystConversation(owner_id=owner_id, **payload.model_dump())
    session.add(row); session.commit(); session.refresh(row)
    return ConversationPublic(id=row.id, messages=[])


@router.get('/analyst/conversations/{conversation_id}', response_model=ConversationPublic)
def get_conversation(conversation_id: str, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    row = owned_conversation(session, conversation_id, user.id)
    return ConversationPublic(id=row.id, messages=[message_public(m) for m in conversation_messages(session, row.id)])


@router.post('/analyst/conversations/{conversation_id}/messages', response_model=MessageAccepted, status_code=202)
def create_message(conversation_id: str, payload: MessageCreate, request: Request, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    owner_id = user.id
    row = owned_conversation(session, conversation_id, owner_id)
    previous = replay_message(session, row, payload.content, payload.request_id)
    if previous:
        return previous
    require_configured(request.app)
    task = owned_task(session, row.task_id, owner_id) if row.task_id else None
    if task:
        require_complete(task)
    version = task.updated_at if task else None
    facts = load_task_facts(request.app, task) if task else load_preset_facts(request.app, row.preset_id)
    session.rollback()
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    row = owned_conversation(session, conversation_id, owner_id)
    if task and owned_task(session, row.task_id, owner_id).updated_at != version:
        raise HTTPException(409, '任务已变化，请重新读取结果')
    result = submit_message(request.app, session, row, payload.content, payload.request_id, facts=facts)
    session.commit()
    return result


@router.get('/analyst/conversations/{conversation_id}/events', response_class=StreamingResponse)
def conversation_events(conversation_id: str, request: Request, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    owned_conversation(session, conversation_id, user.id)
    owner_id = user.id

    async def events():
        revisions = {}
        tick = 0
        while not await request.is_disconnected():
            with Session(request.app.state.engine) as fresh:
                conversation = fresh.get(AnalystConversation, conversation_id)
                if not conversation or conversation.owner_id != owner_id:
                    yield 'event: done\ndata: {}\n\n'; return
                rows = conversation_messages(fresh, conversation_id)
                snapshots = [(row.id, row.revision, row.status, message_public(row).model_dump()) for row in rows]
            for mid, revision, _, value in snapshots:
                if revisions.get(mid) != revision:
                    yield f'id: {mid}:{revision}\nevent: message\ndata: {pack(value)}\n\n'
                    revisions[mid] = revision
            if not any(status in {'queued','running'} for _,_,status,_ in snapshots):
                yield 'event: done\ndata: {}\n\n'; return
            tick += 1
            if tick % 40 == 0:
                yield ': keep-alive\n\n'
            await asyncio.sleep(.25)

    return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

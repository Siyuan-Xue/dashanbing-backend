"""Administrator metadata and bounded operational actions only."""
import json
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.api.deps import get_admin_user
from app.database import get_session
from app.models import User
from app.admin_models import AdminAudit
from app.admin_schemas import SettingsPatch, UserPatch, JobAction, JobPage, ForceLogout
from app.services import admin as service
from app.services import admin_jobs

router=APIRouter(prefix='/admin',tags=['administrator'],dependencies=[Depends(get_admin_user)])


def page_result(items,total,page,page_size):
    return dict(items=items,total=total,page=page,page_size=page_size)


@router.get('/overview')
def overview(request:Request,session:Session=Depends(get_session)):
    return service.overview(request.app,session)


@router.get('/settings')
def settings(request:Request,session:Session=Depends(get_session)):
    return service.settings_public(request.app,session)


@router.patch('/settings')
def change_settings(payload:SettingsPatch,request:Request,session:Session=Depends(get_session),actor:User=Depends(get_admin_user)):
    return service.change_settings(request.app,session,actor.id,payload)


@router.get('/users')
def users(request:Request,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),q:str=Query('',max_length=100),
          is_active:bool|None=None,session:Session=Depends(get_session)):
    filters=[User.role=='user']
    if q:
        escaped=q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        filters.append(or_(User.username.ilike('%'+escaped+'%',escape='\\'),User.email.ilike('%'+escaped+'%',escape='\\')))
    if is_active is not None:
        filters.append(User.is_active==is_active)
    total=session.exec(select(func.count()).select_from(User).where(*filters)).one()
    rows=session.exec(select(User).where(*filters).order_by(User.id).offset((page-1)*page_size).limit(page_size)).all()
    return page_result([service.user_public(request.app,session,row) for row in rows],total,page,page_size)


@router.patch('/users/{user_id}')
def change_user(user_id:int,payload:UserPatch,request:Request,session:Session=Depends(get_session),actor:User=Depends(get_admin_user)):
    return service.change_user(request.app,session,actor.id,user_id,payload)


@router.post('/users/{user_id}/force-logout',status_code=204)
def force_logout(user_id:int,payload:ForceLogout,request:Request,session:Session=Depends(get_session),actor:User=Depends(get_admin_user)):
    service.change_user(request.app,session,actor.id,user_id,reason=payload.reason)
    return Response(status_code=204)


@router.get('/jobs',response_model=JobPage)
def jobs(request:Request,kind:Literal['video','ai','preset']|None=None,status:str|None=Query(None,max_length=30),
         page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),session:Session=Depends(get_session)):
    candidates=[];total=0
    for category,model in admin_jobs.MODELS.items():
        if kind and kind!=category:
            continue
        filters=[model.status==status] if status else []
        total+=session.exec(select(func.count()).select_from(model).where(*filters)).one()
        rows=session.exec(select(model).where(*filters).order_by(model.created_at.desc(),model.id).limit(page*page_size)).all()
        candidates.extend((row.created_at,category,row) for row in rows)
    candidates.sort(key=lambda item:(-item[0].timestamp(),item[1],item[2].id))
    selected=candidates[(page-1)*page_size:page*page_size]
    return page_result([admin_jobs.metadata(request.app,session,category,row) for _,category,row in selected],total,page,page_size)


@router.post('/jobs/actions')
def job_action(payload:JobAction,request:Request,session:Session=Depends(get_session),actor:User=Depends(get_admin_user)):
    return admin_jobs.act(request.app,session,actor.id,payload)


@router.get('/audit')
def audit(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),session:Session=Depends(get_session)):
    total=session.exec(select(func.count()).select_from(AdminAudit)).one()
    rows=session.exec(select(AdminAudit).order_by(AdminAudit.created_at.desc(),AdminAudit.id).offset((page-1)*page_size).limit(page_size)).all()
    return page_result([dict(id=r.id,actor_id=r.actor_id,action=r.action,reason=r.reason,target_kind=r.target_kind,
        target_ids=json.loads(r.target_ids_json),changes=json.loads(r.changes_json),created_at=r.created_at) for r in rows],total,page,page_size)


@router.get('/deployment')
def deployment(request:Request,session:Session=Depends(get_session)):
    return service.deployment(request.app,session)

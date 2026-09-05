from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_session
from app.models import User
from app.analyst_schemas import AnalystContext, AnalystContextUpdate
from app.services.analyst_facts import load_task_facts
from app.services.tasks import begin_write, task_or_404
from app.services.training_profiles import task_context, update_task_context


router = APIRouter(tags=["analyst-context"])


def _facts(request, task):
    if task.status == "expired":
        raise HTTPException(status_code=410, detail="Task result has expired")
    if task.status != "completed":
        raise HTTPException(status_code=409, detail="Task result is not completed")
    try:
        return load_task_facts(request.app, task)
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="Task result not found") from None


@router.get("/tasks/{task_id}/analyst/context", response_model=AnalystContext)
def get_context(task_id: str, request: Request, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    task = task_or_404(task_id, user.id, session)
    return task_context(session, task, _facts(request, task))


@router.put("/tasks/{task_id}/analyst/context", response_model=AnalystContext)
def put_context(task_id: str, payload: AnalystContextUpdate, request: Request,
                user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    # Read/hash outside the write lock, then recheck lifecycle under the lock.
    task = task_or_404(task_id, user.id, session)
    facts = _facts(request, task)
    session.rollback()
    begin_write(session)
    task = task_or_404(task_id, user.id, session)
    if task.status != "completed":
        raise HTTPException(status_code=409, detail="Task result is not completed")
    result = update_task_context(session, task, facts, payload)
    session.commit()
    return result

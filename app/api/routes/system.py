from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user


router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(get_current_user)])


@router.get("/readiness")
def readiness(request: Request) -> dict:
    return request.app.state.readiness.report()

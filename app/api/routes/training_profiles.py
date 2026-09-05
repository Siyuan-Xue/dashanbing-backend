from fastapi import APIRouter, Depends, Response
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.database import get_session
from app.models import User
from app.analyst_models import TrainingProfile, utc_now
from app.analyst_schemas import ObservationPublic, TrainingProfileCreate, TrainingProfilePublic, TrainingProfileUpdate
from app.services.tasks import begin_write
from app.services.training_profiles import delete_profile, invalidate_memory, profile_history, profile_or_404


router = APIRouter(tags=["training-profiles"])


@router.get("/training-profiles", response_model=list[TrainingProfilePublic])
def list_profiles(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.exec(select(TrainingProfile).where(TrainingProfile.owner_id == user.id).order_by(TrainingProfile.created_at.desc(), TrainingProfile.id)).all()


@router.post("/training-profiles", response_model=TrainingProfilePublic, status_code=201)
def create_profile(payload: TrainingProfileCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    begin_write(session)
    profile = TrainingProfile(owner_id=user.id, **payload.model_dump())
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@router.patch("/training-profiles/{profile_id}", response_model=TrainingProfilePublic)
def update_profile(profile_id: str, payload: TrainingProfileUpdate, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    begin_write(session)
    profile = profile_or_404(session, user.id, profile_id)
    fields = payload.model_dump(exclude_unset=True)
    if any(getattr(profile, key) != value for key, value in fields.items()):
        for key, value in fields.items():
            setattr(profile, key, value)
        profile.updated_at = utc_now()
        session.add(profile)
        invalidate_memory(session, user.id, profile_ids={profile_id})
    session.commit()
    session.refresh(profile)
    return profile


@router.delete("/training-profiles/{profile_id}", status_code=204)
def remove_profile(profile_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    begin_write(session)
    delete_profile(session, user.id, profile_id)
    session.commit()
    return Response(status_code=204)


@router.get("/training-profiles/{profile_id}/history", response_model=list[ObservationPublic])
def history(profile_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return profile_history(session, user.id, profile_id)

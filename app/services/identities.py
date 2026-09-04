from sqlmodel import Session, select

from app.models import User, UserIdentity
from app.security import normalize_identity


def user_identity_values(user: User) -> set[str]:
    values = {normalize_identity(user.username)}
    if user.email is not None:
        values.add(normalize_identity(user.email))
    return values


def find_user_by_identity(session: Session, identity: str) -> User | None:
    record = session.get(UserIdentity, identity)
    if record is not None:
        user = session.get(User, record.user_id)
        if user is not None:
            return user
    for user in session.exec(select(User)):
        if identity in user_identity_values(user):
            return user
    return None


def ensure_user_identities(session: Session, user: User) -> None:
    if user.id is None:
        session.flush()
    for value in user_identity_values(user):
        record = session.get(UserIdentity, value)
        if record is None:
            session.add(UserIdentity(value=value, user_id=user.id))
        elif record.user_id != user.id:
            raise ValueError("User identity is already assigned")

from collections.abc import Generator

from fastapi import Request
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.engine import Engine


DEFAULT_DATABASE_URL = "sqlite:///./demo.db"


def create_database_engine(database_url: str) -> Engine:
    """Create the application database engine with SQLite-safe settings."""
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def create_tables(engine: Engine) -> None:
    """Create all SQLModel tables registered by the application."""
    SQLModel.metadata.create_all(engine)


def get_session(request: Request) -> Generator[Session, None, None]:
    """Provide one SQLModel session for the current request."""
    with Session(request.app.state.engine) as session:
        yield session

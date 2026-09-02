from collections.abc import Generator

from fastapi import Request
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine


DEFAULT_DATABASE_URL = "sqlite:///./runtime/app.db"


def create_database_engine(database_url: str) -> Engine:
    """Create the application database engine with SQLite-safe settings."""
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
    return engine


def create_tables(engine: Engine) -> None:
    """Create all SQLModel tables registered by the application."""
    SQLModel.metadata.create_all(engine)


def get_session(request: Request) -> Generator[Session, None, None]:
    """Provide one SQLModel session for the current request."""
    with Session(request.app.state.engine) as session:
        yield session

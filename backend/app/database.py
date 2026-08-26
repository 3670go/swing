from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import Settings


def normalize_database_url(database_url: str) -> str:
    """Normalize Supabase Postgres URLs for SQLAlchemy's psycopg 3 dialect."""
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    raise ValueError("DATABASE_URL must be a PostgreSQL connection URL")


def alembic_database_url(database_url: str) -> str:
    """Escape percent-encoded credentials for Alembic's ConfigParser."""
    return normalize_database_url(database_url).replace("%", "%%")


class Database:
    """SQLAlchemy connection boundary for Supabase Postgres."""

    def __init__(self, settings: Settings) -> None:
        self.engine: Engine = create_engine(
            normalize_database_url(settings.database_dsn),
            poolclass=NullPool,
            pool_pre_ping=True,
            connect_args={"prepare_threshold": None},
        )
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Commit one application transaction or roll it back on failure."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    def ping(self) -> None:
        """Execute a narrow database readiness query."""
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def close(self) -> None:
        """Release local SQLAlchemy engine resources."""
        self.engine.dispose()

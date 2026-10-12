"""Synchronous SQLAlchemy connection boundary for application SQL.

The services use positional ``?`` parameters. This small adapter converts them to
SQLAlchemy named binds so values remain parameterized across SQLite and PostgreSQL.
Schema changes are owned by Alembic; importing this module never creates tables.
"""
from contextlib import contextmanager
from pathlib import Path
import re
from threading import Lock
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool, StaticPool

from app.config import get_settings


class DatabaseUnavailable(RuntimeError):
    """Raised when a configured database cannot be reached or used."""


class DatabaseResult:
    def __init__(self, result):
        self._result = result

    def fetchone(self):
        return self._result.mappings().fetchone() if self._result.returns_rows else None

    def fetchall(self):
        return self._result.mappings().fetchall() if self._result.returns_rows else []

    @property
    def rowcount(self):
        return self._result.rowcount


class DatabaseConnection:
    def __init__(self, connection: Connection):
        self._connection = connection

    def execute(self, statement: str, parameters: Any = ()) -> DatabaseResult:
        if isinstance(parameters, dict):
            bound = parameters
            sql = statement
        else:
            values = tuple(parameters or ())
            index = 0

            def replace_placeholder(_match):
                nonlocal index
                name = f"p{index}"
                index += 1
                return f":{name}"

            sql = re.sub(r"\?", replace_placeholder, statement)
            if index != len(values):
                raise ValueError("SQL parameter count does not match placeholders")
            bound = {f"p{i}": value for i, value in enumerate(values)}
        result = self._connection.execute(text(sql), bound)
        return DatabaseResult(result)

    @property
    def dialect_name(self) -> str:
        return self._connection.dialect.name


def normalize_database_url(value: str) -> str:
    """Normalize PostgreSQL URLs to psycopg 3 while preserving URL options."""
    try:
        url = make_url(value)
    except Exception:
        raise ValueError("DATABASE_URL is not a valid SQLAlchemy URL") from None
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def configured_database_url() -> str:
    settings = get_settings()
    raw = settings.database_url.strip()
    if not raw:
        raise RuntimeError("DATABASE_URL must be configured")
    url = normalize_database_url(raw)
    if settings.app_env.casefold() == "production" and not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("Production requires DATABASE_URL to point to PostgreSQL.")
    if not (url.startswith("postgresql+psycopg://") or url.startswith("sqlite:")):
        raise RuntimeError("DATABASE_URL must use PostgreSQL or explicitly configured SQLite.")
    return url


_ENGINES: dict[str, Engine] = {}
_ENGINE_LOCK = Lock()


def _engine_for_url(url: str) -> Engine:
    with _ENGINE_LOCK:
        if url in _ENGINES:
            return _ENGINES[url]
        engine = _create_engine(url)
        _ENGINES[url] = engine
        return engine


def _create_engine(url: str) -> Engine:
    parsed = make_url(url)
    if parsed.drivername.startswith("sqlite"):
        database = parsed.database or ""
        if database not in {"", ":memory:"}:
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        if database in {"", ":memory:"}:
            engine = create_engine(url, poolclass=StaticPool, connect_args={"check_same_thread": False, "timeout": 10})
        else:
            engine = create_engine(url, poolclass=NullPool, connect_args={"check_same_thread": False, "timeout": 10})

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_engine(
        url,
        pool_size=5,
        max_overflow=2,
        pool_timeout=20,
        pool_recycle=1800,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 10},
    )


def get_engine() -> Engine:
    return _engine_for_url(configured_database_url())


@contextmanager
def connection():
    """Yield a transaction-scoped connection and roll back on every exception."""
    engine = get_engine()
    with engine.begin() as conn:
        yield DatabaseConnection(conn)


def check_database() -> None:
    try:
        with connection() as conn:
            conn.execute("SELECT 1 FROM users LIMIT 0")
    except SQLAlchemyError:
        raise DatabaseUnavailable("Configured database is unavailable or the operation failed.") from None


def dispose_engines() -> None:
    """Test helper to close cached pools between isolated test databases."""
    with _ENGINE_LOCK:
        for engine in _ENGINES.values():
            engine.dispose()
        _ENGINES.clear()

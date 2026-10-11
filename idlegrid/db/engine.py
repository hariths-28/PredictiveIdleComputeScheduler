"""SQLAlchemy engine configuration for the MySQL database."""

from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event, make_url
from sqlalchemy.exc import SQLAlchemyError


class DatabaseUnavailable(RuntimeError):
    """Raised when the configured database cannot be used."""


def get_engine(url: str | None = None) -> Engine:
    """Return the cached SQLAlchemy engine for the configured database URL."""
    database_url = url or os.environ.get("IDLEGRID_DB_URL")
    if not database_url:
        raise DatabaseUnavailable("IDLEGRID_DB_URL is not set and no database URL was provided")
    return _engine_for_url(database_url)


@lru_cache(maxsize=4)
def _engine_for_url(url: str) -> Engine:
    """Build and cache an engine with the project's MySQL connection settings."""
    try:
        parsed_url = make_url(url)
        if parsed_url.drivername != "mysql+pymysql":
            raise DatabaseUnavailable("IDLEGRID_DB_URL must use the mysql+pymysql driver")
        engine = create_engine(
            url,
            pool_size=10,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=1800,
            isolation_level="READ COMMITTED",
        )
    except (SQLAlchemyError, ValueError) as exc:
        raise DatabaseUnavailable("IDLEGRID_DB_URL is invalid or unsupported") from exc

    event.listen(engine, "connect", _set_session_timezone)
    event.listen(engine, "handle_error", _raise_database_unavailable)
    return engine


def _set_session_timezone(dbapi_connection: object, connection_record: object) -> None:
    """Set every MySQL connection's session time zone to UTC."""
    del connection_record
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SET time_zone = '+00:00'")
    finally:
        cursor.close()


def _raise_database_unavailable(exception_context: object) -> None:
    """Wrap disconnects without hiding query, integrity, or schema errors."""
    if exception_context.is_disconnect:
        original = exception_context.original_exception
        raise DatabaseUnavailable("The configured MySQL database is unavailable") from original

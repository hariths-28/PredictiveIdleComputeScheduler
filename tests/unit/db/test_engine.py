"""Tests for database engine configuration and safe errors."""

from collections.abc import Iterator
from unittest.mock import Mock, call

import pytest

from idlegrid.db import engine as db_engine


@pytest.fixture(autouse=True)
def clear_engine_cache() -> Iterator[None]:
    db_engine._engine_for_url.cache_clear()
    yield
    db_engine._engine_for_url.cache_clear()


def test_get_engine_uses_environment_url_and_expected_pool_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IDLEGRID_DB_URL", "mysql+pymysql://user:password@localhost/idlegrid")
    expected_engine = Mock()
    create_engine = Mock(return_value=expected_engine)
    listen = Mock()

    monkeypatch.setattr(db_engine, "create_engine", create_engine)
    monkeypatch.setattr(db_engine.event, "listen", listen)
    assert db_engine.get_engine() is expected_engine
    assert db_engine.get_engine() is expected_engine

    create_engine.assert_called_once_with(
        "mysql+pymysql://user:password@localhost/idlegrid",
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
        isolation_level="READ COMMITTED",
    )
    assert listen.call_args_list == [
        call(expected_engine, "connect", db_engine._set_session_timezone),
        call(expected_engine, "handle_error", db_engine._raise_database_unavailable),
    ]


def test_get_engine_requires_environment_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IDLEGRID_DB_URL", raising=False)

    with pytest.raises(db_engine.DatabaseUnavailable, match="IDLEGRID_DB_URL"):
        db_engine.get_engine()


def test_get_engine_rejects_non_mysql_urls() -> None:
    with pytest.raises(db_engine.DatabaseUnavailable, match="mysql\\+pymysql"):
        db_engine.get_engine("sqlite://")


def test_get_engine_registers_mysql_connection_hooks() -> None:
    engine = db_engine.get_engine("mysql+pymysql://user:placeholder@127.0.0.1:3306/idlegrid")

    assert engine.dialect.name == "mysql"
    engine.dispose()


def test_timezone_listener_sets_session_to_utc() -> None:
    cursor = Mock()
    connection = Mock()
    connection.cursor.return_value = cursor

    db_engine._set_session_timezone(connection, object())

    cursor.execute.assert_called_once_with("SET time_zone = '+00:00'")
    cursor.close.assert_called_once_with()


def test_database_error_message_does_not_include_connection_url() -> None:
    context = Mock()
    context.original_exception = RuntimeError("driver error")
    context.is_disconnect = True

    with pytest.raises(db_engine.DatabaseUnavailable, match="configured MySQL") as error:
        db_engine._raise_database_unavailable(context)

    assert "password" not in str(error.value)


def test_non_disconnect_database_error_is_not_mislabeled_unavailable() -> None:
    context = Mock()
    context.is_disconnect = False

    db_engine._raise_database_unavailable(context)

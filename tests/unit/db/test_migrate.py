"""Tests for ordered and repeatable migration application."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from idlegrid.db.migrate import _split_statements, apply_migrations


def test_split_statements_preserves_semicolons_inside_strings() -> None:
    sql = "CREATE TABLE sample (value VARCHAR(20)); INSERT INTO sample VALUES ('a;b');"

    assert _split_statements(sql) == [
        "CREATE TABLE sample (value VARCHAR(20))",
        "INSERT INTO sample VALUES ('a;b')",
    ]


def test_split_statements_ignores_semicolons_in_mysql_comments() -> None:
    sql = "-- owner's rows; remain comments\nCREATE TABLE sample (value INTEGER); /* ; */"

    assert _split_statements(sql) == ["CREATE TABLE sample (value INTEGER)"]


def test_apply_migrations_in_order_and_is_idempotent(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0002_second.sql").write_text(
        "CREATE TABLE second_table (value INTEGER);", encoding="utf-8"
    )
    (migrations / "0001_first.sql").write_text("CREATE TABLE first_table (value INTEGER);", encoding="utf-8")
    engine = create_engine("sqlite://")

    assert apply_migrations(engine, migrations) == ["0001_first.sql", "0002_second.sql"]
    assert apply_migrations(engine, migrations) == []

    with engine.connect() as conn:
        versions = (
            conn.execute(text("SELECT version FROM schema_migrations ORDER BY version")).scalars().all()
        )
        tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'")).scalars().all()

    assert versions == ["0001_first.sql", "0002_second.sql"]
    assert {"first_table", "second_table"}.issubset(tables)
    engine.dispose()


def test_split_statements_does_not_drop_unterminated_statement() -> None:
    assert _split_statements("CREATE TABLE sample (value INTEGER)") == ["CREATE TABLE sample (value INTEGER)"]


@pytest.mark.parametrize("sql", ["", " ; \n ; "])
def test_split_statements_ignores_empty_input(sql: str) -> None:
    assert _split_statements(sql) == []

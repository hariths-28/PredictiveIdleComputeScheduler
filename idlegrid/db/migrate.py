"""Apply ordered SQL migrations to the IdleGrid MySQL database."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from idlegrid.db.engine import DatabaseUnavailable, get_engine

logger = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).with_name("migrations")
_CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(64) PRIMARY KEY,
    applied_at DATETIME(3) NOT NULL
)"""
_MYSQL_TABLE_OPTIONS = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"


def apply_migrations(engine: Engine, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply unapplied migrations and return their version names in order."""
    applied_now: list[str] = []
    current_migration = "schema_migrations bootstrap"
    if not migrations_dir.is_dir():
        raise DatabaseUnavailable(f"Migration directory does not exist: {migrations_dir}")
    try:
        with engine.begin() as conn:
            table_options = _MYSQL_TABLE_OPTIONS if conn.dialect.name == "mysql" else ""
            conn.exec_driver_sql(_CREATE_MIGRATIONS_TABLE + table_options)

        for migration_path in sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            version = migration_path.name
            current_migration = version
            with engine.begin() as conn:
                recorded = conn.execute(
                    text("SELECT 1 FROM schema_migrations WHERE version = :version"),
                    {"version": version},
                ).first()
                if recorded is not None:
                    continue

                sql = migration_path.read_text(encoding="utf-8")
                for statement in _split_statements(sql):
                    conn.exec_driver_sql(statement)
                conn.execute(
                    text(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (:version, :applied_at)"
                    ),
                    {
                        "version": version,
                        "applied_at": datetime.now(UTC).replace(tzinfo=None),
                    },
                )
            applied_now.append(version)
    except (OSError, SQLAlchemyError, DatabaseUnavailable) as exc:
        logger.error("Migration %s failed (%s)", current_migration, type(exc).__name__)
        raise DatabaseUnavailable(f"Database migration failed: {current_migration}") from exc

    return applied_now


def _split_statements(sql: str) -> list[str]:
    """Split migration SQL on semicolons outside strings and comments."""
    statements: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = 0

    while index < len(sql):
        character = sql[index]
        following = sql[index + 1] if index + 1 < len(sql) else ""

        if line_comment:
            if character in "\r\n":
                line_comment = False
                buffer.append(character)
            index += 1
            continue
        if block_comment:
            if character == "*" and following == "/":
                block_comment = False
                index += 2
            else:
                index += 1
            continue
        if quote is not None:
            buffer.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character == "-" and following == "-" and (index + 2 == len(sql) or sql[index + 2].isspace()):
            line_comment = True
            index += 2
            continue
        if character == "#":
            line_comment = True
            index += 1
            continue
        if character == "/" and following == "*":
            block_comment = True
            index += 2
            continue
        elif character in ("'", '"', "`"):
            quote = character
            buffer.append(character)
        elif character == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer.clear()
        else:
            buffer.append(character)
        index += 1

    final_statement = "".join(buffer).strip()
    if final_statement:
        statements.append(final_statement)
    return statements


def main(argv: Sequence[str] | None = None) -> int:
    """Run the migration command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-url", help="Database URL; defaults to IDLEGRID_DB_URL")
    args = parser.parse_args(argv)

    try:
        applied = apply_migrations(get_engine(args.db_url))
    except DatabaseUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if applied:
        print(f"Applied {len(applied)} migration(s): {', '.join(applied)}")
    else:
        print("Database schema is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

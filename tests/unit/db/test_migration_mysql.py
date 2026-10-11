"""MySQL integration coverage for the Appendix C initial migration."""

import os

import pytest
from sqlalchemy import inspect, text

from idlegrid.db.engine import get_engine
from idlegrid.db.migrate import main

pytestmark = pytest.mark.mysql


def test_initial_migration_creates_appendix_c_tables_idempotently() -> None:
    database_url = os.environ.get("IDLEGRID_DB_URL")
    if not database_url:
        pytest.skip("Set IDLEGRID_DB_URL to a disposable, clean MySQL 8 database")

    engine = get_engine(database_url)
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar_one()
        assert str(version).startswith("8."), "Appendix C requires MySQL 8"
        assert not inspect(engine).has_table("schema_migrations"), (
            "Use a clean test database so this test verifies first-time migration"
        )

        assert main([]) == 0
        assert main([]) == 0

        table_names = set(inspect(engine).get_table_names())
        assert {
            "schema_migrations",
            "users",
            "nodes",
            "node_status_events",
            "usage_samples",
            "experiment_runs",
            "hpo_studies",
            "jobs",
            "job_attempts",
            "node_commands",
            "oracle_models",
        }.issubset(table_names)

        with engine.connect() as conn:
            migration_count = conn.execute(
                text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"),
                {"version": "0001_initial.sql"},
            ).scalar_one()
        assert migration_count == 1
    finally:
        engine.dispose()

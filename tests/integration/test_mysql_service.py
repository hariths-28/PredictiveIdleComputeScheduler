"""Checks that the MySQL service CI provides is reachable. Amaan's repository tests (M-P0-2) build on this."""

import os
from urllib.parse import urlparse

import pytest

pytestmark = pytest.mark.mysql

DB_URL = os.environ.get("IDLEGRID_DB_URL")


@pytest.mark.skipif(not DB_URL, reason="IDLEGRID_DB_URL not set (no MySQL available)")
def test_mysql_reachable():
    import pymysql

    u = urlparse(DB_URL.replace("mysql+pymysql://", "mysql://", 1))
    conn = pymysql.connect(
        host=u.hostname,
        port=u.port or 3306,
        user=u.username,
        password=u.password or "",
        database=u.path.lstrip("/") or None,
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            (version,) = cur.fetchone()
        assert version.startswith("8.")
    finally:
        conn.close()

import os

import duckdb
import pytest
from typer.testing import CliRunner

from table_diff.adapters import Database, Policy
from table_diff.cli import app
from table_diff.core import compare


@pytest.fixture
def pair(tmp_path):
    paths = [tmp_path / name for name in ("a.db", "b.db")]
    for path in paths:
        c = duckdb.connect(str(path))
        c.execute("CREATE TABLE trips(id INTEGER, day TIMESTAMP, fare DOUBLE, note VARCHAR)")
        c.execute(
            "INSERT INTO trips VALUES (1, '2024-01-01', 1.234567, ''), (2, '2024-01-02', 2, NULL)"
        )
        c.close()
    return paths


def run(paths, policy=Policy()):
    dbs = [Database(f"duckdb://{p}") for p in paths]
    try:
        return compare(*dbs, "trips", ["id"], "day", policy)
    finally:
        for db in dbs:
            db.close()


def test_equal(pair):
    assert not run(pair)["different"]


def test_missing_changed_duplicate(pair):
    c = duckdb.connect(str(pair[1]))
    c.execute("DELETE FROM trips WHERE id=2")
    c.execute("UPDATE trips SET note=NULL, fare=3 WHERE id=1")
    c.execute("INSERT INTO trips SELECT * FROM trips")
    c.close()
    r = run(pair)
    assert r["differing_keys"] == 2
    assert r["missing_target_keys"] == 1
    assert r["duplicate_target_keys"] == 1
    assert set(r["samples"][0]["columns"]) == {"fare", "note"}


def test_policy(pair):
    c = duckdb.connect(str(pair[1]))
    c.execute("UPDATE trips SET note=NULL, fare=1.234568 WHERE id=1")
    c.close()
    assert not run(pair, Policy(float_digits=4, empty_is_null=True))["different"]
    assert run(pair)["different"]


def test_cli_error_redacts(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "compare",
            "--source",
            "secret-password",
            "--target",
            "x",
            "--table",
            "x",
            "--key",
            "id",
            "--date-col",
            "day",
        ],
    )
    assert result.exit_code == 2
    assert "secret-password" not in result.output


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_DSN"), reason="requires Docker Postgres")
def test_postgres(pair):
    import psycopg

    dsn = os.environ["TEST_POSTGRES_DSN"]
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS trips")
        c.execute("CREATE TABLE trips(note TEXT, fare NUMERIC, day TIMESTAMP, id BIGINT)")
        c.execute("INSERT INTO trips VALUES ('',1.234567,'2024-01-01',1),(NULL,2,'2024-01-02',2)")
    a, b = Database(f"duckdb://{pair[0]}"), Database(dsn)
    try:
        assert not compare(a, b, "trips", ["id"], "day")["different"]
    finally:
        a.close()
        b.close()

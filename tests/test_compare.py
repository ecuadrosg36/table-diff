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
    assert r["exact_unmatched_source_variants_rows"] == 1
    assert r["exact_unmatched_target_variants_rows"] == 2
    assert r["exact_column_multiset_differing_keys"]["fare"] == 1


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


def test_day_move_and_identical_duplicates(pair):
    c = duckdb.connect(str(pair[1]))
    c.execute("UPDATE trips SET day=day + INTERVAL '1 day' WHERE id=1")
    c.close()
    r = run(pair)
    assert r["differing_keys"] == 1
    assert r["samples"][0]["columns"] == ["day"]
    for path in pair:
        c = duckdb.connect(str(path))
        c.execute("INSERT INTO trips SELECT * FROM trips WHERE id=2")
        c.close()
    assert run(pair)["duplicate_source_keys"] == 1


def test_null_key_unicode_and_framing(pair):
    for path in pair:
        c = duckdb.connect(str(path))
        c.execute(
            "INSERT INTO trips VALUES (NULL, NULL, 0, 'é:N;'), (3, '2024-01-03', -0.0, ' x ')"
        )
        c.close()
    assert not run(pair)["different"]
    c = duckdb.connect(str(pair[1]))
    c.execute("UPDATE trips SET note='x' WHERE id=3")
    c.close()
    assert run(pair)["different"]
    assert not run(pair, Policy(trim=True))["different"]


def test_cli_reports_and_exit(pair, tmp_path):
    args = [
        "compare",
        "--source",
        f"duckdb://{pair[0]}",
        "--target",
        f"duckdb://{pair[1]}",
        "--table",
        "trips",
        "--key",
        "id",
        "--date-col",
        "day",
        "--report",
        str(tmp_path / "r.html"),
    ]
    assert CliRunner().invoke(app, args).exit_code == 0
    assert "<!doctype html>" in (tmp_path / "r.html").read_text()
    c = duckdb.connect(str(pair[1]))
    c.execute("DELETE FROM trips")
    c.close()
    assert CliRunner().invoke(app, args).exit_code == 1


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_DSN"), reason="requires Docker Postgres")
def test_cross_adapter_timezone_and_differences(tmp_path):
    import psycopg

    path = tmp_path / "zone.db"
    c = duckdb.connect(str(path))
    c.execute("CREATE TABLE zones(id INTEGER, day TIMESTAMPTZ, note VARCHAR, amount DOUBLE)")
    c.execute("INSERT INTO zones VALUES (1,'2024-01-01 23:30:00-05','é',1.125)")
    c.close()
    dsn = os.environ["TEST_POSTGRES_DSN"]
    with psycopg.connect(dsn, autocommit=True) as pg:
        pg.execute("DROP TABLE IF EXISTS zones")
        pg.execute("CREATE TABLE zones(amount NUMERIC, note TEXT, day TIMESTAMPTZ, id BIGINT)")
        pg.execute("INSERT INTO zones VALUES (1.125,'é','2024-01-02 04:30:00+00',1)")

    def check():
        a, b = Database(f"duckdb://{path}"), Database(dsn)
        try:
            return compare(a, b, "zones", ["id"], "day", Policy(float_digits=2))
        finally:
            a.close()
            b.close()

    assert not check()["different"]
    with psycopg.connect(dsn, autocommit=True) as pg:
        pg.execute("UPDATE zones SET note='', amount=2")
        pg.execute("INSERT INTO zones VALUES (3,'x','2024-01-03',2)")
    result = check()
    assert result["differing_keys"] == 2
    assert result["missing_source_keys"] == 1
    assert result["samples"][0]["columns"] == ["amount", "note"]


def test_duplicate_on_matching_day_is_not_missing_key(pair):
    c = duckdb.connect(str(pair[0]))
    c.execute("INSERT INTO trips VALUES (1, '2024-01-03', 1, 'duplicate')")
    c.close()
    r = run(pair)
    assert r["differing_keys"] == 1
    assert r["missing_target_keys"] == 0
    assert r["duplicate_source_keys"] == 1
    assert r["exact_unmatched_source_variants_rows"] == 1


@pytest.mark.parametrize("postgres", [False, True])
def test_metadata_column_names_and_date_style(tmp_path, postgres):
    if postgres and not os.getenv("TEST_POSTGRES_DSN"):
        pytest.skip("requires Docker Postgres")
    paths = [tmp_path / "reserved-source.db", tmp_path / "reserved-target.db"]
    schema = (
        "CREATE TABLE reserved_columns (_key INTEGER, _day DATE, _hash VARCHAR, _value_0 VARCHAR)"
    )
    insert = "INSERT INTO reserved_columns VALUES (1, DATE '2024-01-31', 'original', 'user alias'), (2, NULL, '', NULL)"
    c = duckdb.connect(str(paths[0]))
    c.execute(schema)
    c.execute(insert)
    c.close()
    if postgres:
        import psycopg

        connection = os.environ["TEST_POSTGRES_DSN"]
        with psycopg.connect(connection, autocommit=True) as pg:
            pg.execute("DROP TABLE IF EXISTS reserved_columns")
            pg.execute(schema)
            pg.execute(insert)
    else:
        connection = f"duckdb://{paths[1]}"
        c = duckdb.connect(str(paths[1]))
        c.execute(schema)
        c.execute(insert)
        c.close()

    def check():
        a, b = Database(f"duckdb://{paths[0]}"), Database(connection)
        try:
            if postgres:
                b.conn.execute("SET LOCAL DateStyle = 'SQL, DMY'")
                assert b.query("SHOW DateStyle")[0][0] == "SQL, DMY"
                # Prove this session would render a generic DATE cast differently.
                assert b.query("SELECT CAST(DATE '2024-01-31' AS VARCHAR)")[0][0] == "31/01/2024"
            return compare(a, b, "reserved_columns", ["_key"], "_day")
        finally:
            a.close()
            b.close()

    assert not check()["different"]
    if postgres:
        with psycopg.connect(connection, autocommit=True) as c:
            c.execute("UPDATE reserved_columns SET _hash='changed' WHERE _key=1")
    else:
        c = duckdb.connect(str(paths[1]))
        c.execute("UPDATE reserved_columns SET _hash='changed' WHERE _key=1")
        c.close()
    result = check()
    assert result["differing_keys"] == 1
    assert result["samples"][0]["columns"] == ["_hash"]
    assert result["samples"][0]["source"][0] != result["samples"][0]["target"][0]
    assert result["exact_column_multiset_differing_keys"] == {"_hash": 1}
    assert result["exact_unmatched_source_variants_rows"] == 1
    assert result["exact_unmatched_target_variants_rows"] == 1

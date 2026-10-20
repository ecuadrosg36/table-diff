"""Real TLC month -> DuckDB -> Docker Postgres, with disjoint verified mutations."""

import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import duckdb
import psycopg

from table_diff.adapters import Database
from table_diff.cli import markdown
from table_diff.core import compare

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".demo"
URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet"
DSN = "postgresql://postgres:demo@localhost:55432/demo"


def main():
    DATA.mkdir(exist_ok=True)
    parquet = DATA / "yellow_tripdata_2024-01.parquet"
    if not parquet.exists():
        urllib.request.urlretrieve(URL, parquet)
    docker = shutil.which("docker") or "/Applications/Docker.app/Contents/Resources/bin/docker"
    os.environ["PATH"] = str(Path(docker).parent) + os.pathsep + os.environ.get("PATH", "")
    name = "table-diff-demo"
    exists = subprocess.run([docker, "inspect", name], capture_output=True).returncode == 0
    if not exists:
        subprocess.run(
            [
                docker,
                "run",
                "-d",
                "--name",
                name,
                "--label",
                f"ao.session={os.environ.get('AO_SESSION_ID', 'standalone')}",
                "-e",
                "POSTGRES_PASSWORD=demo",
                "-e",
                "POSTGRES_DB=demo",
                "-p",
                "127.0.0.1:55432:5432",
                "postgres:16",
            ],
            check=True,
        )
    else:
        subprocess.run([docker, "start", name], check=True, capture_output=True, timeout=30)
    for attempt in range(60):
        try:
            pg = psycopg.connect(DSN, autocommit=True)
            break
        except psycopg.OperationalError:
            time.sleep(1)
    else:
        raise RuntimeError("Postgres did not become ready")
    source = DATA / "source.duckdb"
    source.unlink(missing_ok=True)
    db = duckdb.connect(str(source))
    schema = db.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet}')").fetchall()
    # Synthetic stable migration key and NULL/empty probe are explicitly documented.
    db.execute(
        f"CREATE TABLE trips AS SELECT row_number() OVER ()::BIGINT AS trip_id, "
        f"*, ''::VARCHAR AS synthetic_note FROM read_parquet('{parquet}')"
    )
    desc = db.execute("DESCRIBE trips").fetchall()
    mapping = {
        "BIGINT": "BIGINT",
        "INTEGER": "INTEGER",
        "DOUBLE": "DOUBLE PRECISION",
        "TIMESTAMP": "TIMESTAMP",
        "VARCHAR": "TEXT",
    }
    from table_diff.adapters import ident

    pg.execute("DROP VIEW IF EXISTS probe")
    pg.execute("DROP TABLE IF EXISTS trips")
    pg.execute(
        "CREATE TABLE trips (" + ",".join(f"{ident(r[0])} {mapping[r[1]]}" for r in desc) + ")"
    )
    csv = DATA / "trips.csv"
    db.execute(f"COPY trips TO '{csv}' (FORMAT CSV, HEADER FALSE, NULL '\\N')")
    with pg.cursor().copy(
        "COPY trips FROM STDIN WITH (FORMAT CSV, HEADER FALSE, NULL '\\N')"
    ) as copy:
        with csv.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                copy.write(chunk)
    # Disjoint mutations: full busiest day; then 100-row probes on surviving days.
    dropped_day, dropped_count = db.execute(
        "SELECT tpep_pickup_datetime::DATE, count(*) FROM trips GROUP BY 1 ORDER BY 2 DESC LIMIT 1"
    ).fetchone()
    ids = [
        r[0]
        for r in db.execute(
            "SELECT trip_id FROM trips WHERE "
            f"tpep_pickup_datetime::DATE <> DATE '{dropped_day}' AND VendorID=2 "
            "AND fare_amount <> round(fare_amount,0) ORDER BY trip_id LIMIT 300"
        ).fetchall()
    ]
    assert len(ids) == 300
    groups = [ids[i : i + 100] for i in (0, 100, 200)]
    mutations = [
        (
            "dropped_day",
            f"DELETE FROM trips WHERE tpep_pickup_datetime::DATE = '{dropped_day}'",
            dropped_count,
        ),
        (
            "vendor_timestamp_shift",
            "UPDATE trips SET tpep_pickup_datetime=tpep_pickup_datetime "
            f"+ INTERVAL '1 hour' WHERE trip_id IN ({','.join(map(str, groups[0]))})",
            100,
        ),
        (
            "fare_rounding",
            "UPDATE trips SET fare_amount=round(fare_amount::numeric,0) "
            f"WHERE trip_id IN ({','.join(map(str, groups[1]))})",
            100,
        ),
        (
            "empty_to_null",
            "UPDATE trips SET synthetic_note=NULL "
            f"WHERE trip_id IN ({','.join(map(str, groups[2]))})",
            100,
        ),
        ("duplicates", f"INSERT INTO trips SELECT * FROM trips WHERE trip_id={ids[0]}", 1),
    ]
    manifest = dict(
        dataset=URL,
        sha256=hashlib.file_digest(parquet.open("rb"), "sha256").hexdigest(),
        original_schema=schema,
        synthetic_columns=["trip_id", "synthetic_note"],
        dropped_day=str(dropped_day),
        mutations=[],
        probe_ids=dict(timestamp=groups[0], fare=groups[1], null_empty=groups[2]),
        duplicate_trip_id=ids[0],
    )
    for name_, sql, expected in mutations:
        cursor = pg.execute(sql)
        assert cursor.rowcount == expected
        manifest["mutations"].append(dict(name=name_, affected=cursor.rowcount))
    db.close()
    start = time.perf_counter()
    a, b = Database(f"duckdb://{source}"), Database(DSN)
    try:
        result = compare(a, b, "trips", ["trip_id"], "tpep_pickup_datetime", sample_limit=5)
    finally:
        a.close()
        b.close()
    elapsed = time.perf_counter() - start
    assert result["different"]
    assert result["missing_target_keys"] == dropped_count
    assert result["differing_keys"] == dropped_count + 300
    assert result["duplicate_target_keys"] == 1
    # Individually verify each mutation via the comparator on small SQL-backed views.
    checks = {}
    for label, group, column in zip(
        ("timestamp", "fare", "null_empty"),
        groups,
        ("tpep_pickup_datetime", "fare_amount", "synthetic_note"),
    ):
        predicate = ",".join(map(str, group))
        db = duckdb.connect(str(source))
        db.execute(
            f"CREATE OR REPLACE VIEW probe AS SELECT * FROM trips WHERE trip_id IN ({predicate})"
        )
        db.close()
        pg.execute(
            f"CREATE OR REPLACE VIEW probe AS SELECT * FROM trips WHERE trip_id IN ({predicate})"
        )
        a, b = Database(f"duckdb://{source}"), Database(DSN)
        try:
            probe = compare(a, b, "probe", ["trip_id"], "tpep_pickup_datetime", sample_limit=1)
        finally:
            a.close()
            b.close()
        assert probe["differing_keys"] == 100
        assert column in probe["samples"][0]["columns"]
        checks[label] = dict(
            differing_keys=probe["differing_keys"], exact_column=column, actual_output=probe
        )
    manifest["verification"] = checks
    (ROOT / "docs/demo-manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str) + "\n"
    )
    report = "# Measured TLC demo\n\n"
    report += (
        f"Actual local run: {elapsed:.2f} seconds for main comparison. Full January 2024 file.\n\n"
    )
    report += "All five injected mutation classes verified with assertions; synthetic key and string probe explicitly added.\n\n"
    report += markdown(result)
    (ROOT / "docs/demo-report.md").write_text(report)
    # Exercise public CLI and explicitly accept only its expected differences exit.
    cli = subprocess.run(
        [
            "uv",
            "run",
            "table-diff",
            "compare",
            "--source",
            f"duckdb://{source}",
            "--target",
            DSN,
            "--table",
            "probe",
            "--key",
            "trip_id",
            "--date-col",
            "tpep_pickup_datetime",
            "--report",
            str(DATA / "cli-report.md"),
            "--sample-limit",
            "1",
        ]
    )
    assert cli.returncode == 1, f"Expected difference exit 1, received {cli.returncode}"
    pg.close()
    print(f"Verified all mutations. Main comparison {elapsed:.2f}s; docs/demo-report.md")


if __name__ == "__main__":
    main()

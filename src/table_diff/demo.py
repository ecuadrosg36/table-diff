"""Build a fake "legacy" orders table and a "migrated" copy, then compare them twice.

The migrated copy has 3 real bugs and 3 kinds of harmless noise that migrations often add:

Real bugs                                     Noise
- refunded orders dropped on one day          - float drift on amount (1e-9)
- a retry loaded some orders twice            - country padded with spaces (CHAR column)
- a status mapping turned shipped into paid   - empty notes stored as NULL

The first run compares raw values and drowns in noise. The second run uses the noise rules and
reports only the 3 bugs. All data is generated; nothing comes from a real company.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

import duckdb

from table_diff.diff import compare
from table_diff.options import DiffOptions
from table_diff.report import DiffReport, to_markdown
from table_diff.sql import quote_literal

DEFAULT_ROWS = 1_000_000
DAYS = 30
DROPPED_DAY = "2026-01-17"
DUPLICATED_DAY = "2026-01-09"
REMAPPED_DAYS = ("2026-01-22", "2026-01-23")
DUPLICATED_ROWS = 75
REMAPPED_EVERY = 997

LEGACY_SQL = f"""
SELECT i AS order_id,
       DATE '2026-01-01' + CAST(i % {DAYS} AS INTEGER) AS order_date,
       1 + (i * 7919) % 50000 AS customer_id,
       CAST(((i * 37) % 100000) / 100.0 AS DECIMAL(12, 2)) AS amount,
       ['paid', 'shipped', 'refunded'][1 + CAST(i % 7 % 3 AS INTEGER)] AS status,
       ['PE', 'US', 'MX', 'CO'][1 + CAST(i % 4 AS INTEGER)] AS country,
       CASE WHEN i % 5 = 0 THEN '' ELSE 'gift wrap' END AS notes
FROM range(1, $rows + 1) t(i)
"""

MIGRATED_SQL = f"""
WITH moved AS (
    SELECT order_id, order_date, customer_id,
           CAST(amount AS DOUBLE) + 1e-9 AS amount,                                -- noise
           CASE WHEN status = 'shipped'
                     AND order_date IN (DATE '{REMAPPED_DAYS[0]}', DATE '{REMAPPED_DAYS[1]}')
                     AND order_id % {REMAPPED_EVERY} < 50 THEN 'paid'             -- bug: mapping
                ELSE status END AS status,
           rpad(country, 4, ' ') AS country,                                       -- noise
           nullif(notes, '') AS notes                                              -- noise
    FROM legacy
    WHERE NOT (order_date = DATE '{DROPPED_DAY}' AND status = 'refunded')          -- bug: filter
)
SELECT * FROM moved
UNION ALL
(SELECT * FROM moved WHERE order_date = DATE '{DUPLICATED_DAY}'                    -- bug: retry
 ORDER BY order_id LIMIT {DUPLICATED_ROWS})
"""


def build_tables(con: duckdb.DuckDBPyConnection, rows: int, out_dir: Path) -> tuple[Path, Path]:
    """Create both tables and write them to Parquet, the way a migration hands them over."""
    if rows < 1:
        raise ValueError("rows must be at least 1")
    out_dir.mkdir(parents=True, exist_ok=True)
    legacy, migrated = out_dir / "legacy_orders.parquet", out_dir / "migrated_orders.parquet"
    con.execute(f"CREATE OR REPLACE TABLE legacy AS {LEGACY_SQL}", {"rows": rows})
    con.execute(f"CREATE OR REPLACE TABLE migrated AS {MIGRATED_SQL}")
    con.execute(f"COPY legacy TO {quote_literal(str(legacy))} (FORMAT parquet)")
    con.execute(f"COPY migrated TO {quote_literal(str(migrated))} (FORMAT parquet)")
    return legacy, migrated


def run(rows: int = DEFAULT_ROWS, out_dir: Path = Path("demo_data")) -> tuple[DiffReport, DiffReport]:
    with duckdb.connect() as con:
        legacy, migrated = build_tables(con, rows, out_dir)
        base = {"key": ("order_id",), "partition": "order_date"}
        naive = compare(con, str(legacy), str(migrated), DiffOptions(**base))
        rules = DiffOptions(**base, float_decimals=6, trim_strings=True, empty_as_null=True)
        cleaned = compare(con, str(legacy), str(migrated), rules)
    return naive, cleaned


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="table-diff-demo", description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--out", type=Path, default=Path("demo_data"))
    args = parser.parse_args(argv)
    naive, cleaned = run(args.rows, args.out)
    changed = naive.row_counts.get("changed", 0)
    print(
        f"Without noise rules: {len(naive.bad_partitions)} of {len(naive.partitions)} partitions "
        f"differ and {changed:,} rows look changed.\n"
    )
    print("With --float-decimals 6 --trim --empty-as-null:\n")
    print(to_markdown(cleaned))
    return 0

from collections.abc import Iterator

import duckdb
import pytest


@pytest.fixture
def con() -> Iterator[duckdb.DuckDBPyConnection]:
    """In-memory database with a small `source` table; tests build `target` from it."""
    with duckdb.connect() as connection:
        connection.execute(
            """
            CREATE TABLE source AS SELECT * FROM (VALUES
                (1, DATE '2026-01-01', 10.50, 'paid',    'PE', 'note'),
                (2, DATE '2026-01-01', 20.00, 'shipped', 'US', ''),
                (3, DATE '2026-01-02', 30.25, 'paid',    'MX', 'note'),
                (4, DATE '2026-01-02', 40.00, 'refunded','CO', ''),
                (5, DATE '2026-01-03', 50.75, 'paid',    'PE', 'note')
            ) t(id, day, amount, status, country, notes)
            """
        )
        yield connection


def make_target(con: duckdb.DuckDBPyConnection, select_sql: str) -> None:
    con.execute(f"CREATE OR REPLACE TABLE target AS {select_sql}")

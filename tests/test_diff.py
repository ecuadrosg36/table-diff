from datetime import date

import duckdb
import pytest
from conftest import make_target

from table_diff import DiffError, DiffOptions, compare, to_markdown

BY_DAY = DiffOptions(key=("id",), partition="day")


def test_identical_tables_match(con: duckdb.DuckDBPyConnection) -> None:
    make_target(con, "SELECT * FROM source")

    report = compare(con, "source", "target", BY_DAY)

    assert report.is_match
    assert report.rows_source == report.rows_target == 5
    assert report.row_counts == {}


def test_row_order_does_not_matter(con: duckdb.DuckDBPyConnection) -> None:
    make_target(con, "SELECT * FROM source ORDER BY id DESC")

    assert compare(con, "source", "target", BY_DAY).is_match


def test_only_the_partition_with_a_change_is_flagged(con: duckdb.DuckDBPyConnection) -> None:
    make_target(con, "SELECT * REPLACE (CASE WHEN id = 3 THEN 'refunded' ELSE status END AS status) FROM source")

    report = compare(con, "source", "target", BY_DAY)

    assert [p.partition for p in report.bad_partitions] == ["2026-01-02"]
    assert report.row_counts == {"changed": 1}
    assert report.column_counts["status"] == 1
    assert report.column_counts["amount"] == 0
    cell = report.cells[0]
    assert (cell.key, cell.column, cell.source_value, cell.target_value) == ({"id": 3}, "status", "paid", "refunded")


def test_missing_extra_and_duplicate_rows(con: duckdb.DuckDBPyConnection) -> None:
    make_target(
        con,
        """
        SELECT * FROM source WHERE id <> 1
        UNION ALL SELECT * FROM source WHERE id = 5
        UNION ALL SELECT 6, DATE '2026-01-02', 1.0, 'paid', 'PE', 'x'
        """,
    )

    report = compare(con, "source", "target", BY_DAY)

    assert report.row_counts == {"missing_in_target": 1, "duplicate_key": 1, "extra_in_target": 1}
    assert report.row_samples["missing_in_target"] == [{"id": 1}]
    assert report.row_samples["duplicate_key"] == [{"id": 5}]
    assert report.row_samples["extra_in_target"] == [{"id": 6}]


def test_partition_missing_in_target(con: duckdb.DuckDBPyConnection) -> None:
    make_target(con, "SELECT * FROM source WHERE day <> DATE '2026-01-03'")

    report = compare(con, "source", "target", BY_DAY)

    statuses = {p.partition: p.status for p in report.partitions}
    assert statuses["2026-01-03"] == "missing_in_target"


def test_composite_key(con: duckdb.DuckDBPyConnection) -> None:
    make_target(con, "SELECT * REPLACE (CASE WHEN id = 2 THEN 'XX' ELSE country END AS country) FROM source")

    report = compare(con, "source", "target", DiffOptions(key=("id", "day")))

    assert report.row_samples["changed"] == [{"id": 2, "day": date(2026, 1, 1)}]


def test_without_partition_everything_is_one_partition(con: duckdb.DuckDBPyConnection) -> None:
    make_target(con, "SELECT * FROM source WHERE id <> 4")

    report = compare(con, "source", "target", DiffOptions(key=("id",)))

    assert [p.partition for p in report.partitions] == ["(all rows)"]
    assert report.row_counts == {"missing_in_target": 1}


def test_timestamp_partition_is_grouped_by_day(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE TABLE ts_source AS SELECT id, CAST(day AS TIMESTAMP) + INTERVAL 5 HOUR AS at FROM source")
    con.execute("CREATE TABLE ts_target AS SELECT * FROM ts_source")

    report = compare(con, "ts_source", "ts_target", DiffOptions(key=("id",), partition="at"))

    assert [p.partition for p in report.partitions] == ["2026-01-01", "2026-01-02", "2026-01-03"]


def test_schema_differences_are_reported(con: duckdb.DuckDBPyConnection) -> None:
    make_target(con, "SELECT * EXCLUDE (notes) REPLACE (CAST(amount AS DOUBLE) AS amount), 1 AS loaded FROM source")

    report = compare(con, "source", "target", BY_DAY)

    assert report.schema.only_in_source == ("notes",)
    assert report.schema.only_in_target == ("loaded",)
    assert report.schema.type_changes[0][0] == "amount"
    assert not report.is_match


def test_ignored_columns_are_not_compared(con: duckdb.DuckDBPyConnection) -> None:
    make_target(con, "SELECT * REPLACE ('changed' AS notes) FROM source")

    assert compare(con, "source", "target", DiffOptions(key=("id",), ignore=("notes",))).is_match


def test_missing_key_column_fails_clearly(con: duckdb.DuckDBPyConnection) -> None:
    make_target(con, "SELECT * EXCLUDE (id) FROM source")

    with pytest.raises(DiffError, match="id not found in target"):
        compare(con, "source", "target", BY_DAY)


def test_unreadable_table_fails_clearly(con: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(DiffError, match="Cannot read"):
        compare(con, "source", "does_not_exist", BY_DAY)


def test_max_samples_limits_examples(con: duckdb.DuckDBPyConnection) -> None:
    make_target(con, "SELECT * REPLACE ('x' AS status) FROM source")

    report = compare(con, "source", "target", DiffOptions(key=("id",), max_samples=2))

    assert report.row_counts["changed"] == 5
    assert len(report.row_samples["changed"]) == 2
    assert len(report.cells) == 2


def test_markdown_report_lists_every_section(con: duckdb.DuckDBPyConnection) -> None:
    make_target(
        con,
        """
        SELECT * EXCLUDE (notes) REPLACE (CASE WHEN id = 3 THEN 'x' ELSE status END AS status), 1 AS loaded
        FROM source WHERE id <> 1
        """,
    )

    text = to_markdown(compare(con, "source", "target", BY_DAY))

    for expected in (
        "DIFFERENCES FOUND",
        "## Schema",
        "Columns only in source: notes",
        "Columns only in target: loaded",
        "## Partitions with differences",
        "| missing_in_target | 1 |",
        "`status`: 1",
        "| id=3 | status | paid | x |",
    ):
        assert expected in text

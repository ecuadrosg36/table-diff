import duckdb
import pytest
from conftest import make_target

from table_diff import DiffError, DiffOptions, compare

KEY = ("id",)


@pytest.mark.parametrize(
    ("target_sql", "rule"),
    [
        ("SELECT * REPLACE (CAST(amount AS DOUBLE) + 1e-9 AS amount) FROM source", {"float_decimals": 6}),
        ("SELECT * REPLACE (rpad(country, 4, ' ') AS country) FROM source", {"trim_strings": True}),
        ("SELECT * REPLACE (nullif(notes, '') AS notes) FROM source", {"empty_as_null": True}),
    ],
    ids=["float-drift", "padded-strings", "empty-vs-null"],
)
def test_each_noise_rule_removes_its_noise(con: duckdb.DuckDBPyConnection, target_sql: str, rule: dict) -> None:
    make_target(con, target_sql)

    assert not compare(con, "source", "target", DiffOptions(key=KEY)).is_match
    assert compare(con, "source", "target", DiffOptions(key=KEY, **rule)).is_match


def test_decimal_and_double_with_same_value_are_equal(con: duckdb.DuckDBPyConnection) -> None:
    make_target(con, "SELECT * REPLACE (CAST(amount AS DOUBLE) AS amount) FROM source")

    report = compare(con, "source", "target", DiffOptions(key=KEY))

    assert report.row_counts == {}
    assert report.schema.type_changes  # still reported, but not counted as data differences


def test_noise_rules_do_not_hide_real_changes(con: duckdb.DuckDBPyConnection) -> None:
    make_target(con, "SELECT * REPLACE (CASE WHEN id = 1 THEN amount + 0.01 ELSE amount END AS amount) FROM source")

    report = compare(con, "source", "target", DiffOptions(key=KEY, float_decimals=6))

    assert report.row_counts == {"changed": 1}


def test_null_is_not_equal_to_text_null(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE TABLE a AS SELECT 1 AS id, CAST(NULL AS VARCHAR) AS v")
    con.execute("CREATE TABLE b AS SELECT 1 AS id, 'NULL' AS v")

    assert compare(con, "a", "b", DiffOptions(key=KEY)).row_counts == {"changed": 1}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"key": ()},
        {"key": ("id", "id")},
        {"key": ("id",), "float_decimals": 99},
        {"key": ("id",), "max_samples": -1},
        {"key": ("id",), "partition": "id"},
    ],
)
def test_invalid_options_fail_fast(kwargs: dict) -> None:
    with pytest.raises(DiffError):
        DiffOptions(**kwargs)

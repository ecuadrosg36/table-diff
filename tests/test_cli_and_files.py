import json
from pathlib import Path

import duckdb
import pytest

from table_diff import DiffError
from table_diff.cli import EXIT_DIFFERENCES, EXIT_ERROR, EXIT_MATCH, main
from table_diff.demo import DUPLICATED_ROWS, run
from table_diff.demo import main as demo_main
from table_diff.sql import quote_ident, quote_literal, relation


@pytest.fixture
def files(tmp_path: Path) -> tuple[Path, Path, Path]:
    same, changed = tmp_path / "a.parquet", tmp_path / "b.csv"
    duckdb.sql("SELECT range AS id, range * 2 AS v FROM range(10)").write_parquet(str(same))
    duckdb.sql("SELECT range AS id, CASE WHEN range = 3 THEN -1 ELSE range * 2 END AS v FROM range(10)").write_csv(
        str(changed)
    )
    return same, changed, tmp_path


def test_cli_exit_code_is_zero_when_tables_match(files, capsys) -> None:
    same, _, _ = files

    assert main([str(same), str(same), "--key", "id"]) == EXIT_MATCH
    assert "MATCH" in capsys.readouterr().out


def test_cli_exit_code_is_one_on_differences_and_json_works(files, capsys) -> None:
    same, changed, _ = files

    code = main([str(same), str(changed), "--key", "id", "--format", "json"])

    result = json.loads(capsys.readouterr().out)
    assert code == EXIT_DIFFERENCES
    assert result["is_match"] is False
    assert result["row_counts"] == {"changed": 1}


def test_cli_exit_code_is_two_when_input_is_bad(files, capsys) -> None:
    same, _, _ = files

    assert main([str(same), str(same), "--key", "nope"]) == EXIT_ERROR
    assert "not found" in capsys.readouterr().err


def test_cli_reads_tables_from_a_duckdb_file(files) -> None:
    _, _, folder = files
    db = folder / "warehouse.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE SCHEMA legacy; CREATE TABLE legacy.orders AS SELECT range AS id FROM range(3)")
        con.execute("CREATE TABLE orders AS SELECT range AS id FROM range(3)")

    assert main(["legacy.orders", "orders", "--key", "id", "--db", str(db)]) == EXIT_MATCH


def test_names_and_paths_are_quoted() -> None:
    assert quote_ident('we"ird') == '"we""ird"'
    assert quote_literal("it's") == "'it''s'"
    assert relation("data/o'rders.parquet") == "read_parquet('data/o''rders.parquet')"
    assert relation("raw.orders") == '"raw"."orders"'
    with pytest.raises(DiffError):
        relation("raw..orders")


def test_demo_finds_exactly_the_planted_bugs(tmp_path: Path) -> None:
    naive, cleaned = run(rows=30_000, out_dir=tmp_path)

    assert len(naive.bad_partitions) == len(naive.partitions)  # noise hides everything
    assert len(cleaned.bad_partitions) == 4
    assert cleaned.row_counts["duplicate_key"] == DUPLICATED_ROWS
    assert set(cleaned.row_counts) == {"missing_in_target", "duplicate_key", "changed"}
    assert {c for c, n in cleaned.column_counts.items() if n} == {"status"}
    assert cleaned.rows_source - (cleaned.rows_target - DUPLICATED_ROWS) == cleaned.row_counts["missing_in_target"]


def test_demo_command_prints_both_runs(tmp_path: Path, capsys) -> None:
    assert demo_main(["--rows", "3000", "--out", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert "Without noise rules: 30 of 30 partitions differ" in out
    assert "DIFFERENCES FOUND" in out

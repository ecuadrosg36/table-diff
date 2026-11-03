"""The comparison itself, in three passes that each look at less data than the one before.

1. Partitions: row count and an order-independent hash sum per partition. Equal partitions are done.
2. Rows: only inside partitions that differ, match rows by key and compare one hash per row.
3. Cells: only for rows that changed, find which columns differ.

All the heavy work runs as SQL inside DuckDB, so the data never has to fit in Python.
"""

import time

import duckdb

from table_diff.options import DiffError, DiffOptions
from table_diff.report import CellDiff, DiffReport, PartitionDiff, SchemaDiff
from table_diff.sql import normalized, partition_expr, quote_ident, relation

SOURCE_VIEW = "__td_source"
TARGET_VIEW = "__td_target"
ROWS_TABLE = "__td_rows"
BAD_PARTITIONS = "__td_bad_partitions"


def compare(con: duckdb.DuckDBPyConnection, source: str, target: str, options: DiffOptions) -> DiffReport:
    started = time.perf_counter()
    source_types = _column_types(con, relation(source))
    target_types = _column_types(con, relation(target))
    _check_required_columns(options, source_types, target_types)
    columns = _compared_columns(options, source_types, target_types)

    _create_view(con, SOURCE_VIEW, relation(source), source_types, columns, options)
    _create_view(con, TARGET_VIEW, relation(target), target_types, columns, options)
    partitions = _compare_partitions(con)

    row_counts: dict[str, int] = {}
    row_samples: dict[str, list[dict[str, object]]] = {}
    column_counts: dict[str, int] = {}
    cells: tuple[CellDiff, ...] = ()
    if any(p.status != "match" for p in partitions):
        _create_row_table(con, options.key, partitions)
        row_counts, row_samples = _row_findings(con, options)
        column_counts = _column_counts(con, options.key, columns)
        cells = _cell_examples(con, options, columns)

    return DiffReport(
        source=source,
        target=target,
        rows_source=sum(p.rows_source for p in partitions),
        rows_target=sum(p.rows_target for p in partitions),
        schema=_schema_diff(options, source_types, target_types),
        partitions=partitions,
        row_counts=row_counts,
        row_samples=row_samples,
        column_counts=column_counts,
        cells=cells,
        seconds=time.perf_counter() - started,
    )


def _column_types(con: duckdb.DuckDBPyConnection, rel: str) -> dict[str, str]:
    try:
        rows = con.execute(f"DESCRIBE SELECT * FROM {rel}").fetchall()
    except duckdb.Error as error:
        raise DiffError(f"Cannot read {rel}: {error}") from error
    return {name: column_type for name, column_type, *_ in rows}


def _check_required_columns(options: DiffOptions, source: dict[str, str], target: dict[str, str]) -> None:
    required = [*options.key, *([options.partition] if options.partition else [])]
    for side, types in (("source", source), ("target", target)):
        missing = [column for column in required if column not in types]
        if missing:
            raise DiffError(f"Column(s) {', '.join(missing)} not found in {side}.")


def _compared_columns(options: DiffOptions, source: dict[str, str], target: dict[str, str]) -> tuple[str, ...]:
    skip = {*options.key, options.partition, *options.ignore}
    return tuple(column for column in source if column in target and column not in skip)


def _schema_diff(options: DiffOptions, source: dict[str, str], target: dict[str, str]) -> SchemaDiff:
    ignored = set(options.ignore)
    return SchemaDiff(
        only_in_source=tuple(c for c in source if c not in target and c not in ignored),
        only_in_target=tuple(c for c in target if c not in source and c not in ignored),
        type_changes=tuple((c, source[c], target[c]) for c in source if c in target and source[c] != target[c]),
    )


def _create_view(
    con: duckdb.DuckDBPyConnection,
    name: str,
    rel: str,
    types: dict[str, str],
    columns: tuple[str, ...],
    options: DiffOptions,
) -> None:
    keys = ", ".join(quote_ident(k) for k in options.key)
    values = [normalized(c, types[c], options) for c in columns]
    value_columns = "".join(f", {expr} AS __v{i}" for i, expr in enumerate(values))
    row_hash = f"hash(list_value({', '.join(values)}))" if values else "hash(0)"
    part = partition_expr(options.partition, types.get(options.partition or ""))
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW {name} AS "
        f"SELECT {keys}, {part} AS __part{value_columns}, {row_hash} AS __hash FROM {rel}"
    )


def _compare_partitions(con: duckdb.DuckDBPyConnection) -> tuple[PartitionDiff, ...]:
    summary = "SELECT __part, count(*) AS n, sum(CAST(__hash AS HUGEINT)) AS h FROM {} GROUP BY __part"
    rows = con.execute(
        f"""
        SELECT __part, coalesce(s.n, 0), coalesce(t.n, 0),
               CASE WHEN t.n IS NULL THEN 'missing_in_target'
                    WHEN s.n IS NULL THEN 'extra_in_target'
                    WHEN s.n = t.n AND s.h = t.h THEN 'match'
                    ELSE 'mismatch' END
        FROM ({summary.format(SOURCE_VIEW)}) s
        FULL OUTER JOIN ({summary.format(TARGET_VIEW)}) t USING (__part)
        ORDER BY __part
        """
    ).fetchall()
    return tuple(PartitionDiff(str(p), int(ns), int(nt), status) for p, ns, nt, status in rows)


def _create_row_table(
    con: duckdb.DuckDBPyConnection, key: tuple[str, ...], partitions: tuple[PartitionDiff, ...]
) -> None:
    bad = [(p.partition,) for p in partitions if p.status != "match"]
    con.execute(f"CREATE OR REPLACE TEMP TABLE {BAD_PARTITIONS} (part VARCHAR)")
    con.executemany(f"INSERT INTO {BAD_PARTITIONS} VALUES (?)", bad)
    keys = ", ".join(quote_ident(k) for k in key)
    per_key = (
        f"SELECT {keys}, count(*) AS n, min(__hash) AS h FROM {{}} "
        f"WHERE __part IN (SELECT part FROM {BAD_PARTITIONS}) GROUP BY {keys}"
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {ROWS_TABLE} AS
        SELECT {keys},
               CASE WHEN t.n IS NULL THEN 'missing_in_target'
                    WHEN s.n IS NULL THEN 'extra_in_target'
                    WHEN s.n > 1 OR t.n > 1 THEN 'duplicate_key'
                    WHEN s.h <> t.h THEN 'changed'
                    ELSE 'equal' END AS finding
        FROM ({per_key.format(SOURCE_VIEW)}) s
        FULL OUTER JOIN ({per_key.format(TARGET_VIEW)}) t USING ({keys})
        """
    )


def _row_findings(
    con: duckdb.DuckDBPyConnection, options: DiffOptions
) -> tuple[dict[str, int], dict[str, list[dict[str, object]]]]:
    counts = dict(con.execute(f"SELECT finding, count(*) FROM {ROWS_TABLE} GROUP BY finding").fetchall())
    counts.pop("equal", None)
    keys = ", ".join(quote_ident(k) for k in options.key)
    samples = {}
    for finding in counts:
        rows = con.execute(
            f"SELECT {keys} FROM {ROWS_TABLE} WHERE finding = ? ORDER BY {keys} LIMIT ?",
            [finding, options.max_samples],
        ).fetchall()
        samples[finding] = [dict(zip(options.key, row, strict=True)) for row in rows]
    return counts, samples


def _changed_pairs_sql(key: tuple[str, ...]) -> str:
    """Source and target rows side by side, only for keys whose values changed."""
    keys = ", ".join(quote_ident(k) for k in key)
    in_bad = f"__part IN (SELECT part FROM {BAD_PARTITIONS})"
    return (
        f"FROM (SELECT * FROM {ROWS_TABLE} WHERE finding = 'changed') r "
        f"JOIN (SELECT * FROM {SOURCE_VIEW} WHERE {in_bad}) s USING ({keys}) "
        f"JOIN (SELECT * FROM {TARGET_VIEW} WHERE {in_bad}) t USING ({keys})"
    )


def _column_counts(con: duckdb.DuckDBPyConnection, key: tuple[str, ...], columns: tuple[str, ...]) -> dict[str, int]:
    if not columns:
        return {}
    sums = ", ".join(f"sum(CAST(s.__v{i} IS DISTINCT FROM t.__v{i} AS INTEGER))" for i in range(len(columns)))
    row = con.execute(f"SELECT {sums} {_changed_pairs_sql(key)}").fetchone()
    return {column: int(count or 0) for column, count in zip(columns, row, strict=True)}


def _cell_examples(
    con: duckdb.DuckDBPyConnection, options: DiffOptions, columns: tuple[str, ...]
) -> tuple[CellDiff, ...]:
    if not columns or options.max_samples == 0:
        return ()
    keys = ", ".join(f"r.{quote_ident(k)}" for k in options.key)
    pairs = ", ".join(f"s.__v{i}, t.__v{i}" for i in range(len(columns)))
    rows = con.execute(
        f"SELECT {keys}, {pairs} {_changed_pairs_sql(options.key)} ORDER BY {keys} LIMIT ?",
        [options.max_samples],
    ).fetchall()
    cells = []
    for row in rows:
        key = dict(zip(options.key, row[: len(options.key)], strict=True))
        values = row[len(options.key) :]
        for i, column in enumerate(columns):
            source_value, target_value = values[2 * i], values[2 * i + 1]
            if source_value != target_value:
                cells.append(CellDiff(key, column, source_value, target_value))
    return tuple(cells[: options.max_samples])

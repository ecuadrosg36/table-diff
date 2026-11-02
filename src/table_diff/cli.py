"""Command line entry point. Exit code 0 = tables match, 1 = differences, 2 = could not compare.

The exit codes make it usable as a gate in CI or in an orchestrator after each migrated pipeline.
"""

import argparse
import json
import sys
from collections.abc import Sequence

import duckdb

from table_diff.diff import compare
from table_diff.options import DiffError, DiffOptions
from table_diff.report import to_markdown

EXIT_MATCH = 0
EXIT_DIFFERENCES = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="table-diff",
        description="Compare two tables by hash: partition, then row, then cell.",
    )
    parser.add_argument("source", help="Parquet/CSV/JSON file, or a table name in --db")
    parser.add_argument("target", help="Parquet/CSV/JSON file, or a table name in --db")
    parser.add_argument("--key", action="append", required=True, help="Key column (repeat for composite keys)")
    parser.add_argument("--partition", help="Column to check partition by partition, usually a date")
    parser.add_argument("--ignore", action="append", default=[], help="Column to leave out (repeatable)")
    parser.add_argument("--float-decimals", type=int, help="Round floats/decimals before comparing")
    parser.add_argument("--trim", action="store_true", help="Ignore leading/trailing spaces")
    parser.add_argument("--empty-as-null", action="store_true", help="Treat '' and NULL as equal")
    parser.add_argument("--max-samples", type=int, default=10, help="Examples to keep per finding")
    parser.add_argument("--db", default=":memory:", help="DuckDB database file holding the tables")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        options = DiffOptions(
            key=tuple(args.key),
            partition=args.partition,
            ignore=tuple(args.ignore),
            float_decimals=args.float_decimals,
            trim_strings=args.trim,
            empty_as_null=args.empty_as_null,
            max_samples=args.max_samples,
        )
        with duckdb.connect(args.db, read_only=args.db != ":memory:") as con:
            report = compare(con, args.source, args.target, options)
    except (DiffError, duckdb.Error) as error:
        print(f"table-diff: {error}", file=sys.stderr)
        return EXIT_ERROR

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        print(to_markdown(report))
    return EXIT_MATCH if report.is_match else EXIT_DIFFERENCES


if __name__ == "__main__":
    sys.exit(main())

"""Small SQL builders. Every name and path is quoted, never pasted in raw."""

from table_diff.options import DiffError, DiffOptions

FILE_READERS = {
    ".parquet": "read_parquet",
    ".csv": "read_csv_auto",
    ".json": "read_json_auto",
}
FLOAT_TYPES = ("FLOAT", "DOUBLE", "REAL", "DECIMAL")
STRING_TYPES = ("VARCHAR", "CHAR", "TEXT", "STRING")


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def relation(ref: str) -> str:
    """Turn a file path or a (schema.)table name into something you can SELECT FROM."""
    lowered = ref.lower()
    for extension, reader in FILE_READERS.items():
        if lowered.endswith(extension):
            return f"{reader}({quote_literal(ref)})"
    parts = ref.split(".")
    if not all(part.strip() for part in parts):
        raise DiffError(f"Not a valid table name or supported file: {ref!r}")
    return ".".join(quote_ident(part) for part in parts)


def normalized(column: str, column_type: str, options: DiffOptions) -> str:
    """Expression that renders a column as text after the noise rules, so both sides compare equally."""
    expr = quote_ident(column)
    upper = column_type.upper()
    if upper.startswith(FLOAT_TYPES):
        expr = f"CAST({expr} AS DOUBLE)"
        if options.float_decimals is not None:
            expr = f"round({expr}, {int(options.float_decimals)})"
    elif upper.startswith(STRING_TYPES):
        if options.trim_strings:
            expr = f"trim({expr})"
        if options.empty_as_null:
            expr = f"nullif({expr}, '')"
    elif upper.startswith("TIMESTAMP WITH TIME ZONE"):
        expr = f"timezone('UTC', {expr})"
    return f"CAST({expr} AS VARCHAR)"


def partition_expr(column: str | None, column_type: str | None) -> str:
    """Partition label as text. Timestamps are grouped by day; NULL gets its own label."""
    if column is None:
        return "'(all rows)'"
    expr = quote_ident(column)
    if column_type and column_type.upper().startswith("TIMESTAMP"):
        expr = f"CAST({expr} AS DATE)"
    return f"coalesce(CAST({expr} AS VARCHAR), '(null)')"

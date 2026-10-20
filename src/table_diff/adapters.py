"""SQL adapters. New engines implement query, schema, and normalization expressions."""

from dataclasses import dataclass
from typing import Protocol

import duckdb
import psycopg


def ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def table_name(value: str) -> str:
    return ".".join(ident(part) for part in value.split("."))


@dataclass(frozen=True)
class Policy:
    float_digits: int = 6
    timezone: str = "UTC"
    trim: bool = False
    empty_is_null: bool = False


class Adapter(Protocol):
    postgres: bool

    def query(self, sql: str) -> list[tuple]: ...
    def schema(self, table: str) -> dict[str, str]: ...
    def close(self) -> None: ...


class Database:
    def __init__(self, connection: str):
        self.postgres = connection.startswith(("postgresql://", "postgres://"))
        if self.postgres:
            self.conn = psycopg.connect(connection, autocommit=True)
            self.conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            self.conn.execute("SET LOCAL TIME ZONE 'UTC'")
        elif connection.startswith("duckdb://"):
            self.conn = duckdb.connect(connection.removeprefix("duckdb://"), read_only=True)
            self.conn.execute("BEGIN TRANSACTION")
            self.conn.execute("SET TimeZone='UTC'")
        else:
            raise ValueError("Expected duckdb://path or postgresql:// connection")

    def query(self, sql: str) -> list[tuple]:
        return self.conn.execute(sql).fetchall()

    def schema(self, table: str) -> dict[str, str]:
        cursor = self.conn.execute(f"SELECT * FROM {table_name(table)} LIMIT 0")
        if self.postgres:
            return {
                d.name: self.query(f"SELECT format_type({d.type_code}, NULL)")[0][0]
                for d in cursor.description
            }
        return {d[0]: str(d[1]) for d in cursor.description}

    def close(self) -> None:
        self.conn.close()


def family(dtype: str) -> str:
    t = dtype.upper()
    if "TIMESTAMP" in t:
        return "timestamp"
    if t == "DATE":
        return "date"
    if any(x in t for x in ("INT", "DECIMAL", "NUMERIC", "DOUBLE", "FLOAT", "REAL")):
        return "number"
    if any(x in t for x in ("CHAR", "TEXT", "VARCHAR")):
        return "string"
    if t in ("BOOL", "BOOLEAN"):
        return "boolean"
    raise ValueError(f"Unsupported type: {dtype}")


def normalized(col: str, dtype: str, pg: bool, p: Policy) -> str:
    c = ident(col)
    kind = family(dtype)
    if kind == "number":
        # Decimal arithmetic avoids engine-specific binary float formatting.
        s = f"CAST(CAST(round(CAST({c} AS DECIMAL(38,12)), {p.float_digits}) AS DECIMAL(38,{p.float_digits})) AS VARCHAR)"
    elif kind == "timestamp":
        aware = "WITH TIME ZONE" in dtype.upper() or "TIMESTAMPTZ" in dtype.upper()
        zone = "'UTC'" if aware else literal(p.timezone)
        instant = c if aware else f"({c} AT TIME ZONE {zone})"
        utc = f"({instant} AT TIME ZONE 'UTC')"
        s = (
            f"""to_char({utc}, 'YYYY-MM-DD"T"HH24:MI:SS.US')"""
            if pg
            else f"strftime({utc}, '%Y-%m-%dT%H:%M:%S.%f')"
        )
    elif kind == "date":
        s = f"to_char({c}, 'YYYY-MM-DD')" if pg else f"strftime({c}, '%Y-%m-%d')"
    elif kind == "boolean":
        s = f"CASE WHEN {c} THEN 'true' WHEN NOT {c} THEN 'false' END"
    else:
        s = f"CAST({c} AS VARCHAR)"
        if kind == "string" and p.trim:
            s = f"trim({s})"
        if kind == "string" and p.empty_is_null:
            s = f"nullif({s}, '')"
    # Length framing distinguishes null, empty, delimiters, and Unicode values.
    return f"CASE WHEN {s} IS NULL THEN 'N;' ELSE 'V' || length({s}) || ':' || {s} || ';' END"

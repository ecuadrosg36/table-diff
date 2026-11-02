"""What a comparison found. Plain frozen dataclasses so the result is easy to test and serialize."""

from dataclasses import asdict, dataclass, field

ROW_FINDINGS = ("missing_in_target", "extra_in_target", "duplicate_key", "changed")


@dataclass(frozen=True)
class SchemaDiff:
    only_in_source: tuple[str, ...] = ()
    only_in_target: tuple[str, ...] = ()
    type_changes: tuple[tuple[str, str, str], ...] = ()
    """(column, source type, target type)"""


@dataclass(frozen=True)
class PartitionDiff:
    partition: str
    rows_source: int
    rows_target: int
    status: str
    """match, mismatch, missing_in_target or extra_in_target"""


@dataclass(frozen=True)
class CellDiff:
    key: dict[str, object]
    column: str
    source_value: str | None
    target_value: str | None


@dataclass(frozen=True)
class DiffReport:
    source: str
    target: str
    rows_source: int
    rows_target: int
    schema: SchemaDiff
    partitions: tuple[PartitionDiff, ...]
    row_counts: dict[str, int] = field(default_factory=dict)
    """Keys per finding, see ROW_FINDINGS."""
    row_samples: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    column_counts: dict[str, int] = field(default_factory=dict)
    """Changed rows per column."""
    cells: tuple[CellDiff, ...] = ()
    seconds: float = 0.0

    @property
    def bad_partitions(self) -> tuple[PartitionDiff, ...]:
        return tuple(p for p in self.partitions if p.status != "match")

    @property
    def is_match(self) -> bool:
        schema_ok = not (self.schema.only_in_source or self.schema.only_in_target)
        return schema_ok and not self.bad_partitions

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "is_match": self.is_match}


def to_markdown(report: DiffReport) -> str:
    verdict = "MATCH" if report.is_match else "DIFFERENCES FOUND"
    lines = [
        f"# table-diff: {verdict}",
        "",
        f"- Source `{report.source}`: {report.rows_source:,} rows",
        f"- Target `{report.target}`: {report.rows_target:,} rows",
        f"- Partitions checked: {len(report.partitions)}, with differences: {len(report.bad_partitions)}",
        f"- Time: {report.seconds:.2f}s",
        "",
    ]
    lines += _schema_section(report.schema)
    lines += _partition_section(report.bad_partitions)
    lines += _row_section(report)
    lines += _cell_section(report)
    return "\n".join(lines).rstrip() + "\n"


def _schema_section(schema: SchemaDiff) -> list[str]:
    lines = []
    if schema.only_in_source:
        lines.append(f"- Columns only in source: {', '.join(schema.only_in_source)}")
    if schema.only_in_target:
        lines.append(f"- Columns only in target: {', '.join(schema.only_in_target)}")
    for column, source_type, target_type in schema.type_changes:
        lines.append(f"- Type change `{column}`: {source_type} → {target_type}")
    return ["## Schema", "", *lines, ""] if lines else []


def _partition_section(partitions: tuple[PartitionDiff, ...]) -> list[str]:
    if not partitions:
        return []
    lines = [
        "## Partitions with differences",
        "",
        "| partition | source rows | target rows | status |",
        "|---|---:|---:|---|",
    ]
    lines += [f"| {p.partition} | {p.rows_source:,} | {p.rows_target:,} | {p.status} |" for p in partitions]
    return [*lines, ""]


def _row_section(report: DiffReport) -> list[str]:
    counts = {name: report.row_counts.get(name, 0) for name in ROW_FINDINGS}
    if not any(counts.values()):
        return []
    lines = ["## Rows", "", "| finding | keys | examples |", "|---|---:|---|"]
    for name, count in counts.items():
        examples = "; ".join(_format_key(k) for k in report.row_samples.get(name, [])[:3])
        lines.append(f"| {name} | {count:,} | {examples} |")
    if report.column_counts:
        lines += ["", "Changed rows per column:", ""]
        lines += [f"- `{column}`: {count:,}" for column, count in report.column_counts.items() if count]
    return [*lines, ""]


def _cell_section(report: DiffReport) -> list[str]:
    if not report.cells:
        return []
    lines = ["## Cell examples (after normalization)", "", "| key | column | source | target |", "|---|---|---|---|"]
    lines += [f"| {_format_key(c.key)} | {c.column} | {c.source_value} | {c.target_value} |" for c in report.cells]
    return [*lines, ""]


def _format_key(key: dict[str, object]) -> str:
    return ", ".join(f"{name}={value}" for name, value in key.items())

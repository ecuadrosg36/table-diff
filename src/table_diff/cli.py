import html
import json
from pathlib import Path
from typing import Annotated

import typer

from .adapters import Database, Policy
from .core import compare as run_compare

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main():
    """Reconcile database tables with staged SQL fingerprints."""


def markdown(result: dict) -> str:
    fields = (
        "source_rows",
        "target_rows",
        "differing_keys",
        "missing_source_keys",
        "missing_target_keys",
        "duplicate_source_keys",
        "duplicate_target_keys",
    )
    text = "# Table comparison\n\n" + "\n".join(f"- {k}: {result[k]}" for k in fields)
    text += f"\n- mismatching days: {len(result['mismatching_days'])}\n"
    text += "\nHash agreement is probabilistic; normalization can hide intentional differences.\n"
    text += "\n```json\n" + json.dumps(result, indent=2, default=str) + "\n```\n"
    return text


@app.command()
def compare(
    source: Annotated[str, typer.Option()],
    target: Annotated[str, typer.Option()],
    table: Annotated[str, typer.Option()],
    key: Annotated[str, typer.Option()],
    date_col: Annotated[str, typer.Option()],
    report: Path = Path("report.md"),
    float_digits: int = 6,
    timezone: str = "UTC",
    trim: bool = False,
    empty_is_null: bool = False,
    sample_limit: int = 20,
):
    """Compare stable snapshots. Exit 0 equal, 1 differences/duplicates, 2 operational error."""
    databases = []
    try:
        for connection in (source, target):
            databases.append(Database(connection))
        result = run_compare(
            *databases,
            table,
            key.split(","),
            date_col,
            Policy(float_digits, timezone, trim, empty_is_null),
            sample_limit,
        )
        text = markdown(result)
        if report.suffix.lower() == ".html":
            text = (
                '<!doctype html><meta charset="utf-8"><title>Table diff</title><pre>'
                + html.escape(text)
                + "</pre>"
            )
        report.write_text(text)
        typer.echo(
            f"Source {result['source_rows']:,}; target {result['target_rows']:,}; "
            f"days {len(result['mismatching_days'])}; "
            f"differing keys {result['differing_keys']:,}; report {report}"
        )
    except Exception:
        # Connection exceptions can contain credentials. Never echo raw exceptions.
        typer.echo(
            "Operational error: check connection, schema, normalization and report path.", err=True
        )
        raise typer.Exit(2) from None
    finally:
        for db in databases:
            db.close()
    raise typer.Exit(1 if result["different"] else 0)

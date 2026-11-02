"""Compare two tables by hash, from partition to row to cell."""

from table_diff.diff import compare
from table_diff.options import DiffError, DiffOptions
from table_diff.report import DiffReport, to_markdown

__all__ = ["DiffError", "DiffOptions", "DiffReport", "compare", "to_markdown"]

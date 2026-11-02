"""Settings for one comparison, validated up front so bad input fails fast."""

from dataclasses import dataclass

MAX_FLOAT_DECIMALS = 15


class DiffError(ValueError):
    """Raised when the inputs cannot be compared (missing columns, bad options)."""


@dataclass(frozen=True)
class DiffOptions:
    key: tuple[str, ...]
    """Columns that identify a row in both tables."""
    partition: str | None = None
    """Column to split the check by (usually a date). Timestamps are grouped by day."""
    ignore: tuple[str, ...] = ()
    """Columns to leave out, e.g. load timestamps that always differ."""
    float_decimals: int | None = None
    """Round floats and decimals to this many places before comparing."""
    trim_strings: bool = False
    """Ignore leading and trailing spaces, e.g. from CHAR padding."""
    empty_as_null: bool = False
    """Treat empty strings and NULL as the same value."""
    max_samples: int = 10
    """How many example keys and cells to keep per finding."""

    def __post_init__(self) -> None:
        if not self.key:
            raise DiffError("At least one key column is required.")
        if len(set(self.key)) != len(self.key):
            raise DiffError("Key columns must be unique.")
        if self.float_decimals is not None and not 0 <= self.float_decimals <= MAX_FLOAT_DECIMALS:
            raise DiffError(f"float_decimals must be between 0 and {MAX_FLOAT_DECIMALS}.")
        if self.max_samples < 0:
            raise DiffError("max_samples cannot be negative.")
        if self.partition in self.key:
            raise DiffError("The partition column cannot also be a key column.")

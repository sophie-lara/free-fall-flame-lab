"""Explicit, deterministic conversions for canonical normalization units."""

from __future__ import annotations


class UnsupportedUnitError(ValueError):
    """Raised when a source unit has no documented conversion."""


_TO_KPA = {"kpa": 1.0, "pa": 0.001, "bar": 100.0, "atm": 101.325}


def to_kpa(value: float, unit: str) -> float:
    """Convert a documented pressure value to kilopascals without guessing."""
    try:
        return value * _TO_KPA[unit.strip().casefold()]
    except KeyError as error:
        raise UnsupportedUnitError(f"Unsupported pressure unit: {unit!r}") from error

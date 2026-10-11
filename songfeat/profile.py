"""Report which feature columns actually carry information.

Borrowed feature batteries include columns that are meaningless for a
single monophonic vocal line. This finds them before a modelling cycle
does.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

from .record import FeatureRecord


@dataclass
class FeatureProfile:
    name: str
    null_rate: float
    n_distinct: int
    is_constant: bool
    variance: float | None
    dtype: str


def _column_names(records: list[FeatureRecord]) -> list[str]:
    seen: list[str] = []
    for record in records:
        for name in record.features:
            if name not in seen:
                seen.append(name)
    return seen


def profile_records(records: Iterable[FeatureRecord]) -> list[FeatureProfile]:
    records = list(records)
    if not records:
        return []

    profiles: list[FeatureProfile] = []
    for name in _column_names(records):
        values = [r.features.get(name) for r in records]
        present = [v for v in values if v is not None]
        numeric = [v for v in present if isinstance(v, (int, float))
                   and not isinstance(v, bool)]

        # Sample variance needs two points and no non-numeric values mixed
        # in -- statistics.variance raises on fewer than two, and a single
        # string among otherwise-numeric values would make "numeric" a lie.
        variance = (
            statistics.variance(numeric)
            if len(numeric) > 1 and len(numeric) == len(present)
            else None
        )
        distinct = len(set(present))
        profiles.append(
            FeatureProfile(
                name=name,
                null_rate=round(1.0 - len(present) / len(values), 4),
                n_distinct=distinct,
                is_constant=distinct <= 1,
                variance=round(variance, 6) if variance is not None else None,
                dtype=type(present[0]).__name__ if present else "null",
            )
        )
    return profiles


def correlated_pairs(
    records: Iterable[FeatureRecord], threshold: float = 0.95
) -> list[tuple[str, str, float]]:
    """Numeric column pairs whose absolute correlation reaches the threshold."""
    records = list(records)
    if not records:
        return []

    columns: dict[str, list[float]] = {}
    for name in _column_names(records):
        values = [r.features.get(name) for r in records]
        if all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in values
        ):
            columns[name] = [float(v) for v in values]

    found: list[tuple[str, str, float]] = []
    for left, right in combinations(columns, 2):
        a, b = columns[left], columns[right]
        # A zero-variance column makes correlation() divide by zero; it also
        # can't be "correlated" with anything in a way worth reporting.
        if len(a) < 2 or len(set(a)) <= 1 or len(set(b)) <= 1:
            continue
        r = statistics.correlation(a, b)
        if abs(r) >= threshold:
            found.append((left, right, round(r, 4)))
    return found


def weak_for_format(source_format: str) -> set[str]:
    """Field names whose declared ``best_with`` excludes ``source_format``.

    ``best_with`` is recorded on each ``FeatureSpec`` (Task 12) but nothing
    reads it -- the design spec calls that metadata "surfaced by profile".
    This is where it gets surfaced: a column can be fully populated and
    still be a weaker measurement than its name suggests, because the input
    format lacks what the feature needs (e.g. chromaticism inferred from a
    key estimate on MIDI, versus read from real pitch spelling on MusicXML).
    """
    from .features.base import registry

    weak: set[str] = set()
    for spec in registry().values():
        if spec.best_with and source_format not in spec.best_with:
            weak.update(spec.fields)
    return weak

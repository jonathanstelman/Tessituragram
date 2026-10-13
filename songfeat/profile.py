"""Report which feature columns actually carry information.

Borrowed feature batteries include columns that are meaningless for a
single monophonic vocal line. This finds them before a modelling cycle
does.

``FeatureProfile.variance`` is *sample* variance (``statistics.variance``,
``ddof=1``), matching ``pandas.Series.var()``'s default -- not population
variance (``ddof=0``, e.g. ``numpy.var()``'s default), which would read
smaller on the same data.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Sequence

from .record import FeatureRecord

#: Fewer known rows than this and a correlation is noise, not a finding.
MIN_PAIRWISE = 3


@dataclass
class FeatureProfile:
    name: str
    null_rate: float
    n_distinct: int
    is_constant: bool
    variance: float | None
    dtype: str


def _as_mapping(record) -> dict:
    """A record's columns as a plain mapping.

    ``correlated_pairs`` and ``unassessable_columns`` are exercised both
    with real ``FeatureRecord``s (production, and ``profile_records``'
    own tests) and with plain ``{column: value}`` dicts (this module's own
    pairwise-completeness tests, which have no identity fields to carry).
    ``getattr(..., "features", None)`` tells the two apart without the
    caller having to.
    """
    features = getattr(record, "features", None)
    return record if features is None else features


def _column_names(records) -> list[str]:
    seen: list[str] = []
    for record in records:
        for name in _as_mapping(record):
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


def unassessable_columns(records, minimum: int = MIN_PAIRWISE) -> list[str]:
    """Columns with too few known values to correlate against anything.

    Reported rather than dropped: "we could not tell" and "not
    redundant" are different answers, and conflating them is how a
    profiler quietly understates redundancy.
    """
    counts: dict[str, int] = {}
    for record in records:
        for column, value in record.items():
            if isinstance(value, (int, float)) and value is not None:
                counts[column] = counts.get(column, 0) + 1
    columns = {column for record in records for column in record}
    return sorted(column for column in columns if counts.get(column, 0) < minimum)


def correlated_pairs(
    records: Iterable, threshold: float = 0.95, exclude: Sequence[str] = ()
) -> list[tuple[str, str, float]]:
    """Numeric column pairs whose absolute correlation reaches the threshold.

    Compared over each pair's *pairwise-complete* rows -- the rows where
    both columns are known -- rather than discarding a column entirely for
    carrying a null somewhere else. A column that is null on every row of
    one source (every lyrics column on a MIDI-only corpus, say) still gets
    compared against anything it shares real rows with.

    A pair with fewer than ``MIN_PAIRWISE`` shared rows is left out: a
    correlation computed from one or two points is noise, not a finding,
    and reporting it as one would be worse than the blind spot this
    replaces. ``unassessable_columns`` is where that "we could not tell"
    gets reported instead of silently vanishing.
    """
    records = list(records)
    if not records:
        return []

    exclude_set = set(exclude)
    columns: dict[str, list[float | None]] = {}
    for name in _column_names(records):
        if name in exclude_set:
            continue
        values = [_as_mapping(r).get(name) for r in records]
        if all(
            v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))
            for v in values
        ):
            columns[name] = values

    found: list[tuple[str, str, float]] = []
    for left, right in combinations(columns, 2):
        shared = [
            (a, b)
            for a, b in zip(columns[left], columns[right])
            if a is not None and b is not None
        ]
        if len(shared) < MIN_PAIRWISE:
            continue
        a = [float(v) for v, _ in shared]
        b = [float(v) for _, v in shared]
        # A zero-variance column makes correlation() divide by zero; it also
        # can't be "correlated" with anything in a way worth reporting.
        if len(set(a)) <= 1 or len(set(b)) <= 1:
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

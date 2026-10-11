"""Phrase structure, breath demand, and runs."""

from __future__ import annotations

from statistics import fmean
from typing import Any

from ..constants import BREATH_DEMAND_SECONDS
from ..context import PartContext
from ..model import Note, Part, Piece
from .base import feature

PHRASE_FIELDS = (
    "n_phrases", "phrase_longest_seconds", "phrase_mean_seconds",
    "phrase_longest_notes", "n_phrases_over_breath_threshold",
)

RUN_FIELDS = (
    "n_runs", "run_longest_notes", "run_note_share", "runs_per_minute",
    "run_mean_notes_per_second",
)


def _span_seconds(notes: list[Note]) -> float:
    """Onset of the first note to the end of the last."""
    if not notes:
        return 0.0
    start = notes[0].onset_seconds or 0.0
    last = notes[-1]
    return max((last.onset_seconds or 0.0) + (last.duration_seconds or 0.0) - start, 0.0)


@feature(
    name="phrasing", group="vocal", scope="part", source="songfeat",
    description=(
        "REST-DELIMITED SEGMENTS, not breath phrases. A segment is a run of "
        "notes between notated rests of at least PHRASE_GAP_QUARTERS; "
        "n_phrases, phrase_longest_seconds, phrase_mean_seconds and "
        "phrase_longest_notes all describe those segments. Singers breathe "
        "mid-line where no rest is notated, so these do NOT measure breath "
        "demand: on legato writing a segment can run 30-80 seconds and span "
        "many real breaths. n_phrases_over_breath_threshold counts segments "
        "of at least BREATH_DEMAND_SECONDS and saturates accordingly (6 of 8 "
        "on aria I) -- read it as 'long unrested stretches', not 'hard "
        "breaths'. Recalibrating the threshold is a reserved research "
        "question; a seconds-based gap was measured to segment more coarsely, "
        "not more finely."
    ),
    fields=PHRASE_FIELDS,
)
def phrasing(part: Part, piece: Piece) -> dict[str, Any]:
    if part.is_empty:
        return dict.fromkeys(PHRASE_FIELDS)

    phrases = PartContext(part, piece).phrases
    spans = [_span_seconds(p) for p in phrases]
    return {
        "n_phrases": len(phrases),
        "phrase_longest_seconds": round(max(spans), 2) if spans else 0.0,
        "phrase_mean_seconds": round(fmean(spans), 2) if spans else 0.0,
        "phrase_longest_notes": max((len(p) for p in phrases), default=0),
        "n_phrases_over_breath_threshold": sum(
            1 for s in spans if s >= BREATH_DEMAND_SECONDS
        ),
    }


@feature(
    name="runs", group="vocal", scope="part", source="songfeat",
    description=(
        "Fast stepwise or scalar passages: how many, how long, how much of "
        "the line they occupy, and how fast they move."
    ),
    fields=RUN_FIELDS,
)
def runs(part: Part, piece: Piece) -> dict[str, Any]:
    if part.is_empty:
        return dict.fromkeys(RUN_FIELDS)

    context = PartContext(part, piece)
    found = context.runs
    in_runs = sum(len(r) for r in found)
    total_seconds = piece.duration_seconds or 0.0
    run_seconds = sum(_span_seconds(r) for r in found)

    return {
        "n_runs": len(found),
        "run_longest_notes": max((len(r) for r in found), default=0),
        "run_note_share": (
            round(in_runs / len(context.monophonic), 4) if context.monophonic else 0.0
        ),
        "runs_per_minute": (
            round(60.0 * len(found) / total_seconds, 3) if total_seconds else None
        ),
        "run_mean_notes_per_second": (
            round(in_runs / run_seconds, 3) if run_seconds else None
        ),
    }

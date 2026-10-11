"""Tessitura, range and vocal load.

Quartiles are emitted under both duration weighting and count weighting.
The reference spreadsheet and the reference CLI disagree about which one
the published tessitura uses; see docs/superpowers/specs for the numbers.
"""

from __future__ import annotations

from typing import Any

from ..constants import SUSTAINED_MIN_SECONDS
from ..context import PartContext
from ..model import Part, Piece
from .base import feature

TESSITURA_FIELDS = (
    "q0_hz", "q1_hz_dur", "q2_hz_dur", "q3_hz_dur", "q4_hz",
    "q1_hz_cnt", "q2_hz_cnt", "q3_hz_cnt",
    "tessitura_width_dur", "tessitura_width_cnt",
)

LOAD_FIELDS = (
    "cycle_dose", "time_dose_seconds", "rest_seconds", "rest_ratio",
    "sustained_note_count", "sustained_seconds",
)


def midi_to_hz(midi: float) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def weighted_quantile(values, weights, q: float) -> float:
    """Smallest value whose cumulative weight reaches ``q`` of the total."""
    pairs = sorted(zip(values, weights))
    total = sum(w for _, w in pairs)
    if total <= 0:
        return float(pairs[len(pairs) // 2][0])
    target = q * total
    running = 0.0
    for value, weight in pairs:
        running += weight
        if running >= target:
            return float(value)
    return float(pairs[-1][0])


@feature(
    name="tessitura", group="vocal", scope="part", source="songfeat",
    description=(
        "Pitch quartiles in Hz. Emitted twice: weighted by sounding duration "
        "and by note count, because the reference data and the reference "
        "implementation disagree about which defines tessitura."
    ),
    fields=TESSITURA_FIELDS,
)
def tessitura(part: Part, piece: Piece) -> dict[str, Any]:
    if part.is_empty:
        return dict.fromkeys(TESSITURA_FIELDS)

    freqs = [midi_to_hz(n.midi) for n in part.notes]
    durations = [n.duration_seconds or 0.0 for n in part.notes]
    counts = [1.0] * len(freqs)

    q1d = weighted_quantile(freqs, durations, 0.25)
    q2d = weighted_quantile(freqs, durations, 0.50)
    q3d = weighted_quantile(freqs, durations, 0.75)
    q1c = weighted_quantile(freqs, counts, 0.25)
    q2c = weighted_quantile(freqs, counts, 0.50)
    q3c = weighted_quantile(freqs, counts, 0.75)

    return {
        "q0_hz": round(min(freqs), 2),
        "q1_hz_dur": round(q1d, 2),
        "q2_hz_dur": round(q2d, 2),
        "q3_hz_dur": round(q3d, 2),
        "q4_hz": round(max(freqs), 2),
        "q1_hz_cnt": round(q1c, 2),
        "q2_hz_cnt": round(q2c, 2),
        "q3_hz_cnt": round(q3c, 2),
        "tessitura_width_dur": round(q3d - q1d, 2),
        "tessitura_width_cnt": round(q3c - q1c, 2),
    }


@feature(
    name="vocal_load", group="vocal", scope="part", source="songfeat",
    description=(
        "Phonatory load: total vibrations (cycle dose), time spent sounding, "
        "rest, and sustained-note burden."
    ),
    fields=LOAD_FIELDS,
)
def vocal_load(part: Part, piece: Piece) -> dict[str, Any]:
    if part.is_empty:
        return dict.fromkeys(LOAD_FIELDS)

    context = PartContext(part, piece)
    dose = sum(
        midi_to_hz(n.midi) * (n.duration_seconds or 0.0) for n in part.notes
    )
    sounding = sum(n.duration_seconds or 0.0 for n in part.notes)
    total = piece.duration_seconds or sounding
    rest = max(total - sounding, 0.0)

    return {
        "cycle_dose": round(dose, 2),
        "time_dose_seconds": round(sounding, 2),
        "rest_seconds": round(rest, 2),
        "rest_ratio": round(rest / total, 4) if total else None,
        "sustained_note_count": len(context.sustained),
        "sustained_seconds": round(
            sum(n.duration_seconds or 0.0 for n in context.sustained), 2
        ),
    }

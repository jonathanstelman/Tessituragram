"""Tessitura, range and vocal load.

Quartiles are emitted under both duration weighting and count weighting.
The reference spreadsheet and the reference CLI disagree about which one
the published tessitura uses; see docs/superpowers/specs for the numbers.
"""

from __future__ import annotations

from typing import Any

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
    "rest_undefined_reason",
    "sustained_note_count", "sustained_seconds",
)


def midi_to_hz(midi: float) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def weighted_quantile(values, weights, q: float) -> float | None:
    """Smallest value whose cumulative weight reaches ``q`` of the total.

    ``None`` when the weights carry no information at all (every weight
    zero or negative) rather than a middle value dressed up as a measured
    quantile: with zero total weight there is nothing for ``q`` to divide,
    so every quantile asked of a degenerate part would otherwise return the
    same constant regardless of ``q``.
    """
    pairs = sorted(zip(values, weights))
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
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

    # Count weights are always 1.0, so this branch is never degenerate;
    # only the duration-weighted quartiles can come back None.
    q1d = weighted_quantile(freqs, durations, 0.25)
    q2d = weighted_quantile(freqs, durations, 0.50)
    q3d = weighted_quantile(freqs, durations, 0.75)
    q1c = weighted_quantile(freqs, counts, 0.25)
    q2c = weighted_quantile(freqs, counts, 0.50)
    q3c = weighted_quantile(freqs, counts, 0.75)

    width_dur = round(q3d - q1d, 2) if q1d is not None and q3d is not None else None

    return {
        "q0_hz": round(min(freqs), 2),
        "q1_hz_dur": round(q1d, 2) if q1d is not None else None,
        "q2_hz_dur": round(q2d, 2) if q2d is not None else None,
        "q3_hz_dur": round(q3d, 2) if q3d is not None else None,
        "q4_hz": round(max(freqs), 2),
        "q1_hz_cnt": round(q1c, 2),
        "q2_hz_cnt": round(q2c, 2),
        "q3_hz_cnt": round(q3c, 2),
        "tessitura_width_dur": width_dur,
        "tessitura_width_cnt": round(q3c - q1c, 2),
    }


@feature(
    name="vocal_load", group="vocal", scope="part", source="songfeat",
    description=(
        "Phonatory load: total vibrations (cycle dose), time spent sounding, "
        "rest, and sustained-note burden. ``time_dose_seconds`` is the sum of "
        "note durations (a cumulative dose: each voice of a chord phonates), "
        "while ``rest_seconds`` subtracts wall-clock sounding time, which is "
        "the only quantity the piece's total duration can be compared "
        "against. The two differ on any overlapping part; "
        "``rest_undefined_reason`` names why rest is null when it is, and also fires on a zero-length piece, where rest is a real 0.0 but its ratio has no denominator."
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
    # Two different readings of "time spent sounding", kept apart on
    # purpose. The duration sum is cumulative phonatory dose: a four-note
    # chord held for a second is four voice-seconds of phonation, and that
    # is the quantity vocal load is about. Wall-clock sounding time is the
    # union of the sounding intervals (songfeat/context.py:union_seconds).
    #
    # Rest must use the union. Subtracting a dose from the piece's total
    # subtracts voice-seconds from elapsed seconds -- incompatible units,
    # whatever one decides `time_dose_seconds` should mean. On 74 of the
    # 150 corpus arias the sum exceeds elapsed sounding time, and on a
    # chordal part it can exceed the piece's whole duration.
    dose_seconds = sum(n.duration_seconds or 0.0 for n in part.notes)
    sounding = context.sounding_seconds
    total = piece.duration_seconds

    reason: str | None = None
    rest: float | None
    rest_ratio: float | None
    if total is None:
        # The piece's extent is unknown, not zero — rest is undefined,
        # not "no rest at all" (songfeat/model.py:79 makes None legal).
        rest = rest_ratio = None
        reason = "the piece's total duration is unknown, so rest is undefined"
    elif sounding > total + 1e-6:
        # Should be unreachable: a union of intervals inside the piece
        # cannot outlast it. If it happens the input is inconsistent (a
        # note running past the parsed extent), and the honest answer is
        # None with the numbers that did not add up -- never the 0.0 the
        # previous max(..., 0.0) clamp produced, which read as a measured
        # absence of rest.
        rest = rest_ratio = None
        reason = (
            f"wall-clock sounding time ({sounding:g}s) exceeds the piece's "
            f"total duration ({total:g}s); the input is inconsistent"
        )
    else:
        rest = total - sounding
        rest_ratio = round(rest / total, 4) if total else None
        if not total:
            reason = "the piece's total duration is zero, so rest has no ratio"

    return {
        "cycle_dose": round(dose, 2),
        "time_dose_seconds": round(dose_seconds, 2),
        "rest_seconds": round(rest, 2) if rest is not None else None,
        "rest_ratio": rest_ratio,
        "rest_undefined_reason": reason,
        "sustained_note_count": len(context.sustained),
        "sustained_seconds": round(
            sum(n.duration_seconds or 0.0 for n in context.sustained), 2
        ),
    }

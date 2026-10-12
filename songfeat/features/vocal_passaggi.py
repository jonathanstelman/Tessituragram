"""Time spent in, near, and crossing the passaggio zones.

Zones come from constants.PASSAGGI, lifted from the reference
implementation. A zone is a frequency range, not a break point.
"""

from __future__ import annotations

from typing import Any

from ..constants import PASSAGGI, PASSAGGIO_PROXIMITY_SEMITONES
from ..context import split_on_phrase_gaps, union_seconds
from ..model import Note, Part, Piece
from .base import feature
from .vocal_pitch import midi_to_hz


def _build_fields() -> tuple[str, ...]:
    names: list[str] = []
    for voice, registers in PASSAGGI.items():
        for register in registers:
            names.append(f"pass_{voice}_{register}_seconds")
            names.append(f"pass_{voice}_{register}_pct")
        names.append(f"pass_{voice}_crossings")
        names.append(f"pass_{voice}_near_seconds")
        names.append(f"pass_{voice}_longest_span_seconds")
    return tuple(names)


PASSAGGI_FIELDS = _build_fields()

#: Ratio of one semitone, used to widen a zone for proximity.
_SEMITONE = 2.0 ** (1.0 / 12.0)

#: Zone edges are equal-tempered note frequencies rounded to one decimal,
#: so the true pitch can sit up to 0.05 Hz off its own edge (e.g. the
#: medium/middle zone starts at 293.7 Hz while D4 is really 293.6648 Hz).
#: The reference implementation at src/tessitura.py:70 widens every edge
#: by this tolerance for exactly that reason; a strict comparison
#: silently drops notes that land on a boundary.
_EDGE_TOLERANCE_HZ = 0.1


def in_zone(hz: float, zone: tuple[float, float]) -> bool:
    low, high = zone
    return (low - _EDGE_TOLERANCE_HZ) <= hz <= (high + _EDGE_TOLERANCE_HZ)


def zone_overlaps(low_hz: float, high_hz: float, zone: tuple[float, float]) -> bool:
    """Whether the span [low_hz, high_hz] intersects ``zone``.

    Shares ``in_zone``'s edge tolerance rather than re-deriving it, so a
    span endpoint that would count as "in zone" by that function also
    counts here — e.g. D4 (293.6648 Hz) against the medium/middle zone
    (293.7-370.0 Hz), which is only inside at all because of the
    tolerance. Two features computing zone membership with different
    tolerances would disagree about the same note; this is the one
    definition both are required to use.
    """
    low, high = zone
    return low_hz <= (high + _EDGE_TOLERANCE_HZ) and high_hz >= (low - _EDGE_TOLERANCE_HZ)


def near_zone(hz: float, zone: tuple[float, float]) -> bool:
    margin = _SEMITONE ** PASSAGGIO_PROXIMITY_SEMITONES
    low, high = zone
    return (low / margin) <= hz <= (high * margin)


@feature(
    name="passaggi", group="vocal", scope="part", source="songfeat",
    description=(
        "Dwell time, proximity, crossings and longest continuous span in each "
        "of the nine passaggio zones, for high, medium and low voice. "
        "The _seconds columns sum note durations (a cumulative dwell dose, "
        "matching the reference spreadsheet), and _pct divides one of those "
        "by the same kind of total, so it is a share of dwell dose. "
        "_longest_span_seconds is elapsed time instead -- a span is the "
        "length of an interval, so on an overlapping part it is the union of "
        "the stint's sounding intervals and cannot outlast the piece."
    ),
    fields=PASSAGGI_FIELDS,
    citation="Zones from src/tessitura.py:76-84; pedagogical source unconfirmed.",
)
def passaggi(part: Part, piece: Piece) -> dict[str, Any]:
    if part.is_empty:
        return dict.fromkeys(PASSAGGI_FIELDS)

    notes = sorted(part.notes, key=lambda n: (n.onset, n.midi))
    # Sounding time, not piece.duration_seconds: the reference
    # spreadsheet's percentages are of time actually sung, not of the
    # piece's total extent. On aria I that denominator is 164.57s, against
    # whose 25.46s in the low/middle zone the sheet's own 15.56% figure
    # agrees to within its stated tolerance.
    #
    # The sum of note durations, deliberately, and NOT the wall-clock
    # union that `rest_seconds` uses. The dwell times below are duration
    # sums (a cumulative dwell dose, matching the sheet and the pinned
    # ground truth), and a percentage has to divide one of those by a
    # denominator of the same kind:
    #
    #   * dose over dose (this) is a proportion. The numerator's note set
    #     is a subset of the denominator's, so it is bounded by 100, and
    #     because a voice's three registers are disjoint in pitch their
    #     three percentages sum to no more than 100 as well.
    #   * dose over union is not bounded at all: a four-note chord in zone
    #     through a whole piece gives 400%.
    #   * union over union is bounded but measures a different quantity
    #     from the `_seconds` column printed beside it, so the two would
    #     stop corresponding on a chordal part; it also lets a voice's
    #     three registers sum past 100, since separate registers can
    #     sound in the same second. Measured against the ground-truth
    #     sheet it also agreed slightly worse (net -5 of 1350
    #     comparisons across the nine percentage columns).
    #
    # So the over-counting that makes this sum wrong as a wall-clock
    # measure does not make it wrong as a denominator here: it is the same
    # over-count in both halves of the ratio, and it cancels. Spans and
    # rest are a different matter -- they are compared against elapsed
    # time, which is why they use the union.
    sounding = sum(n.duration_seconds or 0.0 for n in notes)
    out: dict[str, Any] = {}

    # A rest is invisible to this model as a Note, so a contiguous span
    # must also break at a rest long enough to count as a phrase gap —
    # otherwise two separate stints in a zone, with a breath between,
    # would be overstated as one unbroken span. The break is derived by
    # the same function PartContext.phrases uses (context.split_on_phrase_gaps),
    # not merely with the same constant, so "a break" cannot drift between
    # the two. It is applied here to every note including chord members,
    # which is the note set this feature's dwell times are defined over
    # (see the note-set rule in songfeat/features/base.py); phrases()
    # applies it to the monophonic reduction, which is the note set
    # phrasing is defined over.
    segments = split_on_phrase_gaps(notes)

    for voice, registers in PASSAGGI.items():
        zones = list(registers.values())

        def inside(note: Note, zones: list = zones) -> bool:
            """Inside any of this voice's registers. One definition, used
            by the crossing count and the span walk alike, so the two
            cannot disagree about where the voice's territory begins."""
            return any(in_zone(midi_to_hz(note.midi), z) for z in zones)

        for register, zone in registers.items():
            seconds = sum(
                (n.duration_seconds or 0.0)
                for n in notes
                if in_zone(midi_to_hz(n.midi), zone)
            )
            out[f"pass_{voice}_{register}_seconds"] = round(seconds, 2)
            # Both halves are duration sums; see `sounding` above for why.
            out[f"pass_{voice}_{register}_pct"] = (
                round(100.0 * seconds / sounding, 2) if sounding else 0.0
            )

        # "Inside" means inside any of the voice's three registers — the
        # zones are disjoint, but a singer anywhere within the voice type's
        # passaggio territory counts, not just inside one named register.
        inside_flags = [inside(n) for n in notes]
        out[f"pass_{voice}_crossings"] = sum(
            1 for a, b in zip(inside_flags, inside_flags[1:]) if a != b
        )
        out[f"pass_{voice}_near_seconds"] = round(
            sum(
                (n.duration_seconds or 0.0)
                for n in notes
                if any(near_zone(midi_to_hz(n.midi), z) for z in zones)
            ),
            2,
        )

        # The longest unbroken stint inside the voice's territory, in
        # elapsed seconds. Accumulating note durations instead would let a
        # chordal part report a 40-second span inside a ten-second piece;
        # the union of the stint's intervals cannot outlast the piece.
        longest = 0.0
        for segment in segments:
            stint: list[Note] = []
            for note in segment:
                if inside(note):
                    stint.append(note)
                else:
                    longest = max(longest, union_seconds(stint))
                    stint = []
            longest = max(longest, union_seconds(stint))
        out[f"pass_{voice}_longest_span_seconds"] = round(longest, 2)

    return out

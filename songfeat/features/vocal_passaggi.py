"""Time spent in, near, and crossing the passaggio zones.

Zones come from constants.PASSAGGI, lifted from the reference
implementation. A zone is a frequency range, not a break point.
"""

from __future__ import annotations

from typing import Any

from ..constants import PASSAGGI, PASSAGGIO_PROXIMITY_SEMITONES
from ..model import Part, Piece
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


def near_zone(hz: float, zone: tuple[float, float]) -> bool:
    margin = _SEMITONE ** PASSAGGIO_PROXIMITY_SEMITONES
    low, high = zone
    return (low / margin) <= hz <= (high * margin)


@feature(
    name="passaggi", group="vocal", scope="part", source="songfeat",
    description=(
        "Dwell time, proximity, crossings and longest continuous span in each "
        "of the nine passaggio zones, for high, medium and low voice."
    ),
    fields=PASSAGGI_FIELDS,
    citation="Zones from src/tessitura.py:76-84; pedagogical source unconfirmed.",
)
def passaggi(part: Part, piece: Piece) -> dict[str, Any]:
    if part.is_empty:
        return dict.fromkeys(PASSAGGI_FIELDS)

    notes = sorted(part.notes, key=lambda n: n.onset)
    # Sounding time (sum of note durations), not piece.duration_seconds:
    # the reference spreadsheet's percentages are of time actually sung,
    # not of the piece's total extent. 25.607 / 164.57 = 15.56%, matching
    # the sheet's figure for aria I exactly.
    sounding = sum(n.duration_seconds or 0.0 for n in notes)
    out: dict[str, Any] = {}

    for voice, registers in PASSAGGI.items():
        zones = list(registers.values())
        for register, zone in registers.items():
            seconds = sum(
                (n.duration_seconds or 0.0)
                for n in notes
                if in_zone(midi_to_hz(n.midi), zone)
            )
            out[f"pass_{voice}_{register}_seconds"] = round(seconds, 2)
            out[f"pass_{voice}_{register}_pct"] = (
                round(100.0 * seconds / sounding, 2) if sounding else 0.0
            )

        inside_flags = [
            any(in_zone(midi_to_hz(n.midi), z) for z in zones) for n in notes
        ]
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

        longest = current = 0.0
        for note, inside in zip(notes, inside_flags):
            current = current + (note.duration_seconds or 0.0) if inside else 0.0
            longest = max(longest, current)
        out[f"pass_{voice}_longest_span_seconds"] = round(longest, 2)

    return out

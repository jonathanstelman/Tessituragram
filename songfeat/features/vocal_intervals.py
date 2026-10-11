"""Leaps and chromaticism.

Chromaticism is measured against the prevailing key signature. MIDI has no
spelling, so this is an inference; MusicXML input yields a stronger reading
of the same columns. That difference is recorded in feature metadata.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from ..constants import LEAP_MIN_SEMITONES, PASSAGGI
from ..context import PartContext
from ..model import Part, Piece
from .base import feature
from .vocal_pitch import midi_to_hz

LEAP_FIELDS = (
    "leap_max_semitones", "leap_share_gt2", "leap_share_gt4", "leap_share_gt7",
    "n_leaps_over_octave", "n_consecutive_leaps", "n_unprepared_leaps",
    "n_leaps_into_extremes", "leap_ascending_share",
    "n_leaps_crossing_passaggio", "interval_mean_abs",
)

CHROMA_FIELDS = (
    "nondiatonic_share", "chromatic_run_longest", "pitch_class_entropy",
    "n_distinct_pitch_classes",
)

#: Semitone offsets of the major scale from the tonic.
MAJOR_STEPS = (0, 2, 4, 5, 7, 9, 11)

#: Tonic pitch class implied by a key signature, indexed by sharp count.
_SHARP_TONICS = (0, 7, 2, 9, 4, 11, 6, 1)
_FLAT_TONICS = (0, 5, 10, 3, 8, 1, 6, 11)


def _tonic_pitch_class(sharps: int) -> int:
    table = _SHARP_TONICS if sharps >= 0 else _FLAT_TONICS
    return table[min(abs(sharps), 7)]


@feature(
    name="leaps", group="vocal", scope="part", source="songfeat",
    description=(
        "Melodic leaps quantified several ways: size, frequency, direction, "
        "preparation, and whether they cross a passaggio zone."
    ),
    fields=LEAP_FIELDS,
)
def leaps(part: Part, piece: Piece) -> dict[str, Any]:
    context = PartContext(part, piece)
    intervals = context.intervals
    if not intervals:
        return dict.fromkeys(LEAP_FIELDS)

    line = context.monophonic
    sizes = [abs(i) for i in intervals]
    leap_indices = [i for i, size in enumerate(sizes) if size >= LEAP_MIN_SEMITONES]
    n = len(intervals)

    midis = [note.midi for note in line]
    low, high = min(midis), max(midis)
    span = high - low
    extreme_low = low + span * 0.1
    extreme_high = high - span * 0.1

    consecutive = sum(
        1 for a, b in zip(leap_indices, leap_indices[1:]) if b == a + 1
    )

    unprepared = 0
    for i in leap_indices:
        if i + 1 >= n:
            unprepared += 1
            continue
        follows = intervals[i + 1]
        same_direction = (follows > 0) == (intervals[i] > 0)
        if abs(follows) >= LEAP_MIN_SEMITONES or same_direction:
            unprepared += 1

    zones = [z for registers in PASSAGGI.values() for z in registers.values()]
    crossing = 0
    for i in leap_indices:
        start_hz, end_hz = midi_to_hz(line[i].midi), midi_to_hz(line[i + 1].midi)
        lo, hi = sorted((start_hz, end_hz))
        if any(lo < zone[1] and hi > zone[0] for zone in zones):
            crossing += 1

    ascending = sum(1 for i in leap_indices if intervals[i] > 0)

    return {
        "leap_max_semitones": max(sizes),
        # Rounded to 6 places, not the 4 used elsewhere for shares: at 4
        # places a repeating fraction like 2/3 rounds to 0.6667, which sits
        # outside pytest.approx's default 1e-6 relative tolerance of the
        # true 0.6666... value. 6 places keeps the output readable while
        # staying well inside that tolerance for any denominator this
        # corpus produces.
        "leap_share_gt2": round(sum(1 for s in sizes if s > 2) / n, 6),
        "leap_share_gt4": round(sum(1 for s in sizes if s > 4) / n, 6),
        "leap_share_gt7": round(sum(1 for s in sizes if s > 7) / n, 6),
        "n_leaps_over_octave": sum(1 for s in sizes if s > 12),
        "n_consecutive_leaps": consecutive,
        "n_unprepared_leaps": unprepared,
        "n_leaps_into_extremes": sum(
            1 for i in leap_indices
            if line[i + 1].midi <= extreme_low or line[i + 1].midi >= extreme_high
        ),
        # Denominator is the *leap* count, not the interval count (unlike
        # leap_share_gt2/gt4/gt7 above, whose denominator is `n` and so
        # stays defined whenever this function runs at all). With zero
        # leaps there is nothing for "share ascending" to divide, so this
        # is the undefined case: None, not a 0.0 that would assert "all
        # leaps descend" about leaps that do not exist.
        "leap_ascending_share": (
            round(ascending / len(leap_indices), 6) if leap_indices else None
        ),
        "n_leaps_crossing_passaggio": crossing,
        "interval_mean_abs": round(sum(sizes) / n, 3),
    }


@feature(
    name="chromaticism", group="vocal", scope="part", source="songfeat",
    description=(
        "Departure from the prevailing diatonic collection. Inferred from the "
        "key signature; stronger for MusicXML input, which carries spelling."
    ),
    fields=CHROMA_FIELDS,
    best_with=("musicxml", "humdrum", "mei"),
)
def chromaticism(part: Part, piece: Piece) -> dict[str, Any]:
    if part.is_empty:
        return dict.fromkeys(CHROMA_FIELDS)

    context = PartContext(part, piece)
    line = context.monophonic

    outside = 0
    for note in line:
        mark = context.prevailing_key(note.onset)
        tonic = _tonic_pitch_class(mark.sharps if mark else 0)
        if (note.midi - tonic) % 12 not in MAJOR_STEPS:
            outside += 1

    longest = current = 0
    for a, b in zip(line, line[1:]):
        current = current + 1 if abs(b.midi - a.midi) == 1 else 0
        longest = max(longest, current + 1 if current else 0)

    counts = Counter(note.midi % 12 for note in line)
    total = sum(counts.values())
    entropy = -sum(
        (c / total) * math.log2(c / total) for c in counts.values() if c
    )

    return {
        "nondiatonic_share": round(outside / len(line), 4),
        "chromatic_run_longest": longest,
        "pitch_class_entropy": round(entropy, 4),
        "n_distinct_pitch_classes": len(counts),
    }

"""Derivations shared across features, computed once per part.

Features read phrases, intervals and runs from here rather than deriving
them locally, so that every feature that mentions a "phrase" means the
same thing.
"""

from __future__ import annotations

from functools import cached_property
from itertools import groupby

from .constants import (
    PHRASE_GAP_QUARTERS,
    RUN_MAX_NOTE_QUARTERS,
    RUN_MIN_NOTES,
    SUSTAINED_MIN_SECONDS,
)
from .model import KeyMark, Note, Part, Piece


def union_seconds(notes: list[Note]) -> float:
    """Wall-clock seconds during which at least one of ``notes`` sounds.

    This is the *union* of each note's [onset, onset + duration] interval,
    which is deliberately not the sum of their durations. The two agree
    only on a strictly monophonic line. Where notes overlap -- a chord, a
    divisi staff, a sustained note under a moving one, or MIDI where a
    note-off lands after the next note-on -- a duration sum counts the
    overlapped stretch once per voice and so exceeds elapsed time. 74 of
    the 150 corpus arias overlap in the vocal part; the worst
    (96-XCVI.mid) sums to 29.3 s more than the 259 s piece lasts.

    That distinction matters because wall-clock sounding time is the only
    quantity a piece's total duration can legally be compared against.
    Subtracting a duration sum from a total mixes two incompatible
    quantities: on a four-note chord repeated through a ten-second piece
    the sum is 40 s, so "rest" comes out negative and only a clamp hides
    it. Subtracting this union cannot exceed the total, so the result is
    an actual measurement.

    A duration sum is still the right quantity for cumulative phonatory
    dose (``time_dose_seconds``), where each voice's phonation really does
    add up. This function is for the wall-clock reading, not that one.
    """
    intervals = sorted(
        (
            (note.onset_seconds or 0.0),
            (note.onset_seconds or 0.0) + (note.duration_seconds or 0.0),
        )
        for note in notes
    )
    total = 0.0
    start = end = None
    for low, high in intervals:
        if start is None:
            start, end = low, high
        elif low <= end:
            end = max(end, high)
        else:
            total += end - start
            start, end = low, high
    if start is not None:
        total += end - start
    return total


def split_on_phrase_gaps(notes: list[Note]) -> list[list[Note]]:
    """Split ``notes`` into runs separated by a phrase-breaking rest.

    The single definition of "a break" in the pipeline. A rest is not a
    ``Note``, so a break is inferred from the gap between one note's end
    and the next note's onset, compared in quarter notes against
    ``PHRASE_GAP_QUARTERS``.

    Callers pass the note set their own measurement is defined over --
    ``PartContext.phrases`` passes the monophonic reduction, ``passaggi``
    passes every note including chord members. Sharing the constant alone
    is not enough: the threshold and the comparison have to come from one
    place, or two features that both say "phrase break" can disagree about
    where one is.
    """
    if not notes:
        return []
    ordered = sorted(notes, key=lambda n: (n.onset, n.midi))
    groups: list[list[Note]] = [[ordered[0]]]
    for previous, current in zip(ordered, ordered[1:]):
        gap = current.onset - (previous.onset + previous.duration)
        if gap >= PHRASE_GAP_QUARTERS:
            groups.append([current])
        else:
            groups[-1].append(current)
    return groups


class PartContext:
    def __init__(self, part: Part, piece: Piece) -> None:
        self.part = part
        self.piece = piece

    @cached_property
    def is_polyphonic(self) -> bool:
        onsets = [n.onset for n in self.part.notes]
        return len(onsets) != len(set(onsets))

    @cached_property
    def monophonic(self) -> list[Note]:
        """One note per onset — the highest, which carries the melody."""
        notes = sorted(self.part.notes, key=lambda n: (n.onset, n.midi))
        return [
            max(group, key=lambda n: n.midi)
            for _, group in groupby(notes, key=lambda n: n.onset)
        ]

    @cached_property
    def intervals(self) -> list[int]:
        line = self.monophonic
        return [b.midi - a.midi for a, b in zip(line, line[1:])]

    @cached_property
    def sounding_seconds(self) -> float:
        """Wall-clock seconds this part is sounding. See ``union_seconds``.

        Not the sum of note durations: on an overlapping part that sum
        exceeds elapsed time and so cannot be subtracted from the piece's
        total. ``vocal_load.time_dose_seconds`` keeps the duration sum,
        deliberately, as a cumulative phonatory dose.
        """
        return union_seconds(self.part.notes)

    @cached_property
    def phrases(self) -> list[list[Note]]:
        """Runs of notes separated by rests longer than the gap threshold.

        Measured over the monophonic reduction; ``split_on_phrase_gaps``
        holds the threshold and the comparison so that every feature that
        says "phrase break" means the same thing.
        """
        return split_on_phrase_gaps(self.monophonic)

    @cached_property
    def runs(self) -> list[list[Note]]:
        """Maximal stretches of consecutive short notes.

        A run is RUN_MIN_NOTES or more notes in a row, each no longer than
        RUN_MAX_NOTE_QUARTERS, with no phrase-breaking rest between them.
        """
        found: list[list[Note]] = []
        for phrase in self.phrases:
            current: list[Note] = []
            for note in phrase:
                if note.duration <= RUN_MAX_NOTE_QUARTERS:
                    current.append(note)
                else:
                    if len(current) >= RUN_MIN_NOTES:
                        found.append(current)
                    current = []
            if len(current) >= RUN_MIN_NOTES:
                found.append(current)
        return found

    @cached_property
    def sustained(self) -> list[Note]:
        return [
            n for n in self.part.notes
            if (n.duration_seconds or 0.0) >= SUSTAINED_MIN_SECONDS
        ]

    def prevailing_key(self, onset: float) -> KeyMark | None:
        marks = [k for k in self.piece.keys if k.onset <= onset]
        return max(marks, key=lambda k: k.onset) if marks else None

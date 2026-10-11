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
    def phrases(self) -> list[list[Note]]:
        """Runs of notes separated by rests longer than the gap threshold."""
        line = self.monophonic
        if not line:
            return []
        phrases: list[list[Note]] = [[line[0]]]
        for previous, current in zip(line, line[1:]):
            gap = current.onset - (previous.onset + previous.duration)
            if gap >= PHRASE_GAP_QUARTERS:
                phrases.append([current])
            else:
                phrases[-1].append(current)
        return phrases

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

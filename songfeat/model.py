"""Format-agnostic representation of a parsed score.

Features are computed against these objects rather than against music21
directly, so that a feature never has to care which file format it came
from, and so tests can build a Piece by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Syllable:
    """One verse's text on one note.

    MusicXML carries one ``<lyric>`` per note per verse, so a word is
    spread across notes and has to be reassembled. ``syllabic`` is
    MusicXML's own marker -- "begin", "middle", "end" or "single" --
    and is what says whether this syllable continues the previous one.
    ``extend`` marks a melisma continuation, which carries no new text.
    """

    number: int
    text: str
    syllabic: str | None = None
    extend: bool = False


@dataclass(frozen=True)
class Note:
    """A single sounding pitch.

    Chord members become separate notes sharing an onset, so that pitch
    statistics do not have to special-case chords.
    """

    midi: int
    onset: float            # quarter notes from the start of the piece
    duration: float         # quarter notes
    part: int               # index into Piece.parts
    onset_seconds: float | None = None
    duration_seconds: float | None = None
    voice: str | None = None
    lyric: str | None = None
    is_chord_member: bool = False
    lyrics: tuple[Syllable, ...] = ()

    @property
    def offset_end(self) -> float:
        return self.onset + self.duration


@dataclass
class Part:
    """One instrumental or vocal line, owning its notes."""

    index: int
    name: str | None = None
    instrument: str | None = None
    notes: list[Note] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.notes)

    @property
    def is_empty(self) -> bool:
        return not self.notes


@dataclass(frozen=True)
class TempoMark:
    onset: float
    bpm: float


@dataclass(frozen=True)
class KeyMark:
    """A notated key signature, not an analysed key."""

    onset: float
    sharps: int             # negative for flats
    mode: str | None = None


@dataclass(frozen=True)
class MeterMark:
    onset: float
    numerator: int
    denominator: int

    @property
    def symbol(self) -> str:
        return f"{self.numerator}/{self.denominator}"


@dataclass
class Piece:
    """A parsed score, normalised across input formats."""

    source_path: str
    source_format: str
    parts: list[Part] = field(default_factory=list)
    tempos: list[TempoMark] = field(default_factory=list)
    keys: list[KeyMark] = field(default_factory=list)
    meters: list[MeterMark] = field(default_factory=list)
    measure_count: int = 0
    quarter_length: float = 0.0
    duration_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # The underlying music21 score, kept for features that need structure
    # the normalised model does not carry. Not used by basic features.
    score: Any = field(default=None, repr=False, compare=False)

    def __len__(self) -> int:
        return len(self.notes)

    @property
    def is_empty(self) -> bool:
        return not self.notes

    @property
    def notes(self) -> list[Note]:
        """Every note across all parts. Piece-scoped features only."""
        return [n for part in self.parts for n in part.notes]

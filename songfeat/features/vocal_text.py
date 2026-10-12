"""Text setting: syllable count and melismatic writing.

A melisma is two or more consecutive notes sung on one syllable. Lyric
events mark the note that begins a syllable, so a note carrying no lyric
continues the previous one.

Notes before the first lyric belong to no syllable — an instrumental
pickup, or a vocal staff where lyrics begin partway through. They are
excluded from melisma grouping entirely rather than merged into a
leading group: a group with no syllable behind it would either inflate
``len(groups)`` past ``n_syllables`` or, worse, report a melisma over a
stretch of notes that carries no text at all. The excluded notes still
count toward the part's note total elsewhere (phrasing, runs, ...); they
just cannot form or extend a melisma. ``notes_per_syllable`` and
``melisma_share`` are accordingly measured over the lyriced portion of
the line, not the whole part, so they describe the text setting itself
rather than being diluted by untexted notes that precede it.
"""

from __future__ import annotations

from typing import Any

from ..context import PartContext
from ..model import Part, Piece
from .base import feature

TEXT_FIELDS = (
    "n_syllables", "notes_per_syllable", "melisma_longest_notes",
    "melisma_share", "n_melismas", "syllables_per_second",
)


@feature(
    name="text_setting", group="vocal", scope="part", source="songfeat",
    description=(
        "Syllable count and melismatic writing: how many notes each syllable "
        "carries, and how much of the lyriced portion of the line is "
        "melismatic. Measured over the monophonic reduction (one note per "
        "onset), because a melisma is a sequence of successive notes; on a "
        "chordal part n_syllables therefore disagrees with "
        "basic.n_lyric_syllables, which counts over every note. Both are "
        "deliberate; see the note-set rule in songfeat/features/base.py."
    ),
    fields=TEXT_FIELDS,
)
def text_setting(part: Part, piece: Piece) -> dict[str, Any]:
    if part.is_empty:
        return dict.fromkeys(TEXT_FIELDS)

    line = PartContext(part, piece).monophonic
    syllables = sum(1 for note in line if note.lyric)

    if syllables == 0:
        return {
            "n_syllables": 0,
            "notes_per_syllable": None,
            "melisma_longest_notes": None,
            "melisma_share": None,
            "n_melismas": None,
            "syllables_per_second": None,
        }

    first_lyric = next(i for i, note in enumerate(line) if note.lyric)
    lyriced = line[first_lyric:]

    groups: list[int] = []
    for note in lyriced:
        if note.lyric:
            groups.append(1)
        else:
            groups[-1] += 1

    melismas = [size for size in groups if size >= 2]
    total_seconds = piece.duration_seconds or 0.0

    return {
        "n_syllables": syllables,
        "notes_per_syllable": round(len(lyriced) / syllables, 3),
        "melisma_longest_notes": max(groups),
        "melisma_share": round(sum(melismas) / len(lyriced), 4),
        "n_melismas": len(melismas),
        "syllables_per_second": (
            round(syllables / total_seconds, 3) if total_seconds else None
        ),
    }

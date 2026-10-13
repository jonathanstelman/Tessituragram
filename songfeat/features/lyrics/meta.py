"""The deterministic half of the lyrics group.

``lyrics_text`` needs no model and no key: it reports what was found in
the file. Provenance lives here too, in Task 11.
"""

from __future__ import annotations

import os
from typing import Any

from ...model import Part, Piece
from ..base import feature
from .assemble import assemble_text
from .questions import Kind, Question, register
from .service import NO_LYRICS

TEXT_FIELDS = (
    "lyrics_word_count",
    "lyrics_verse_count",
    "lyrics_sha256",
    "lyrics_text_path",
    "lyrics_undefined_reason",
)


def sidecar_name(source_path: str | None) -> str | None:
    """The sidecar file's name: the source's stem plus ``.txt``.

    A name rather than a full path, because the directory is the output
    run's business (Task 12) and a feature must stay pure.
    """
    if not source_path:
        return None
    return os.path.splitext(os.path.basename(source_path))[0] + ".txt"


@feature(
    name="lyrics_text", group="lyrics", scope="part", source="songfeat",
    description=(
        "The part's lyrics, reassembled from per-note syllables: word and "
        "verse counts, a hash of the normalised text, and the name of the "
        "sidecar file the full text is written to. Deterministic and "
        "offline -- no classifier is involved. Verse count is the number "
        "of distinct MusicXML lyric numbers found, which may skip."
    ),
    fields=TEXT_FIELDS,
    best_with=("musicxml",),
)
def lyrics_text(part: Part, piece: Piece) -> dict[str, Any]:
    assembled = assemble_text(part)
    if assembled is None:
        return {name: None for name in TEXT_FIELDS} | {
            "lyrics_undefined_reason": NO_LYRICS,
        }
    return {
        "lyrics_word_count": assembled.word_count,
        "lyrics_verse_count": assembled.verse_count,
        "lyrics_sha256": assembled.sha256,
        "lyrics_text_path": sidecar_name(piece.source_path),
        "lyrics_undefined_reason": None,
    }


#: ISO 639-1 codes for the languages this repertoire actually uses, plus
#: escapes. "unspecified" is a real answer: a vocalise has no language.
#: Only English is VALIDATED in this version -- see the group docstring.
LANGUAGES = (
    "en", "it", "de", "fr", "es", "la", "ru", "pt", "cs", "hu", "sv",
    "nl", "other", "unspecified",
)

QUESTIONS = (
    Question(
        id="lyrics_language", kind=Kind.CHOICE, options=LANGUAGES,
        text="What language is this text written in?",
        column="lyrics_language", axis="meta",
    ),
)
register(QUESTIONS)


PROVENANCE_FIELDS = (
    "lyrics_language",
    "clf_model",
    "clf_question_set",
    "clf_classified_at",
    "lyrics_classified_undefined_reason",
)


@feature(
    name="lyrics_provenance", group="lyrics", scope="part", source="songfeat",
    description=(
        "Which model answered, under which question set, and when -- "
        "without these a column means something different next year and "
        "nobody can tell. ``clf_question_set`` distinguishes a lean "
        "``core@v1`` run from a complete ``full@v1`` one, so a partly "
        "classified database cannot be mistaken for a finished one. "
        "``lyrics_classified_undefined_reason`` carries the one reason the "
        "whole classified group is null: no key, no lyrics, text too long, "
        "or a failed call. A sink may decline to write these columns, but "
        "the record always has them."
    ),
    fields=PROVENANCE_FIELDS,
    best_with=("musicxml",),
)
def lyrics_provenance(part: Part, piece: Piece) -> dict[str, Any]:
    from .service import classify_part

    classification = classify_part(part, piece)
    if classification.reason is not None:
        return {name: None for name in PROVENANCE_FIELDS} | {
            "lyrics_classified_undefined_reason": classification.reason,
        }
    answer = classification.answers.get("lyrics_language")
    return {
        "lyrics_language": answer.choice if answer and not answer.error else None,
        "clf_model": classification.model,
        "clf_question_set": classification.question_set,
        "clf_classified_at": classification.classified_at,
        "lyrics_classified_undefined_reason": None,
    }

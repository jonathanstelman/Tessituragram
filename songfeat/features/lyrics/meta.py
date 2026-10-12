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

NO_LYRICS = (
    "this part carries no lyric events; lyric features need a "
    "lyric-bearing format such as MusicXML"
)

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

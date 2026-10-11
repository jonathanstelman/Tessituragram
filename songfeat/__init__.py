"""Structured feature extraction for symbolic music files."""

from .features import extract_part, extract_piece, groups, registry, schema
from .loaders import ParseError, UnsupportedFormatError, load
from .model import Note, Piece

__all__ = [
    "Note",
    "ParseError",
    "Piece",
    "UnsupportedFormatError",
    "extract_part",
    "extract_piece",
    "groups",
    "load",
    "registry",
    "schema",
]


def analyze(path: str, groups_filter=None, drop_trailing_marker: bool = False) -> list[dict]:
    """Parse ``path`` and return one feature record per part.

    Piece-scoped fields (tempo, key, ...) are the same on every record;
    part-scoped fields (pitch range, ...) vary. Merging them here is the
    simplest thing that keeps the output tabular.
    """
    piece = load(path, drop_trailing_marker=drop_trailing_marker)
    piece_fields = extract_piece(piece, groups_filter)
    records = []
    for part in piece.parts:
        part_fields = extract_part(part, piece, groups_filter)
        record = {**piece_fields, **part_fields}
        record["_errors"] = {**piece_fields["_errors"], **part_fields["_errors"]}
        records.append(record)
    return records

"""Structured feature extraction for symbolic music files."""

from .features import extract, groups, registry, schema
from .loaders import ParseError, UnsupportedFormatError, load
from .model import Note, Piece

__all__ = [
    "Note",
    "ParseError",
    "Piece",
    "UnsupportedFormatError",
    "extract",
    "groups",
    "load",
    "registry",
    "schema",
]


def analyze(path: str, groups_filter=None, drop_trailing_marker: bool = False) -> dict:
    """Parse ``path`` and return its feature record."""
    return extract(load(path, drop_trailing_marker=drop_trailing_marker), groups_filter)

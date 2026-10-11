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


def analyze(path: str, groups_filter=None, drop_trailing_marker: bool = False):
    """Parse ``path`` and return one FeatureRecord per part."""
    from .pipeline import analyze_file
    return list(analyze_file(path, groups_filter, drop_trailing_marker))

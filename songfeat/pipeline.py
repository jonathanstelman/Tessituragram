"""load -> prepare -> detect -> extract -> record."""

from __future__ import annotations

from typing import Iterable, Iterator

from .features import base as features_base
from .loaders import ParseError, UnsupportedFormatError, load
from .record import FeatureRecord
from .sinks.base import Sink
from .vocal import detect_vocal


def analyze_file(
    path: str,
    groups_filter: Iterable[str] | None = None,
    drop_trailing_marker: bool = False,
) -> Iterator[FeatureRecord]:
    piece = load(path, drop_trailing_marker=drop_trailing_marker)
    piece_features = features_base.extract_piece(piece, groups_filter)
    piece_errors = piece_features.pop("_errors", {})

    for part in piece.parts:
        part_features = features_base.extract_part(part, piece, groups_filter)
        errors = {**piece_errors, **part_features.pop("_errors", {})}
        evidence = detect_vocal(part, piece)
        yield FeatureRecord(
            source_path=piece.source_path,
            source_format=piece.source_format,
            part_index=part.index,
            part_name=part.name,
            is_vocal_candidate=evidence.is_candidate,
            vocal_confidence=evidence.confidence,
            features={**piece_features, **part_features},
            errors=errors,
        )


def run(
    paths: Iterable[str],
    sink: Sink,
    groups_filter: Iterable[str] | None = None,
    drop_trailing_marker: bool = False,
    on_progress=None,
) -> tuple[int, list[tuple[str, str]]]:
    """Analyse every path into the sink. One bad file never stops the batch."""
    sink.open(features_base.schema(groups_filter))
    count = 0
    failures: list[tuple[str, str]] = []
    try:
        for path in paths:
            try:
                for record in analyze_file(path, groups_filter, drop_trailing_marker):
                    sink.write(record)
                    count += 1
            except (ParseError, UnsupportedFormatError, FileNotFoundError) as exc:
                failures.append((path, f"{type(exc).__name__}: {exc}"))
            except Exception as exc:  # noqa: BLE001
                failures.append((path, f"{type(exc).__name__}: {exc}"))
            if on_progress:
                on_progress(path)
    finally:
        sink.close()
    return count, failures

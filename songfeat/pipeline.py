"""load -> prepare -> detect -> extract -> record."""

from __future__ import annotations

import os
from typing import Iterable, Iterator

from .features import base as features_base
from .loaders import ParseError, UnsupportedFormatError, load
from .record import FeatureRecord
from .sinks.base import Sink
from .vocal import detect_vocal


def _rounded(value: float | None) -> float | None:
    """Round a signal to four places, matching vocal_confidence's own
    rounding, so the four columns visibly sum to the confidence."""
    return None if value is None else round(value, 4)


def _write_sidecar(part, sidecar_dir: str, filename: str) -> None:
    """Write this part's reassembled lyric text next to the output file.

    A sidecar, not a table cell: a 200-word text is unusable in a CSV
    cell, and the Sheets path caps a cell at 50,000 characters. Nothing
    is written when the part turns out to carry no lyrics after all
    (``assemble_text`` returning ``None``), which should not happen if
    ``filename`` came from a real ``lyrics_text_path`` column, but is
    checked rather than assumed.
    """
    from .features.lyrics.assemble import assemble_text

    assembled = assemble_text(part)
    if assembled is None:
        return
    os.makedirs(sidecar_dir, exist_ok=True)
    target = os.path.join(sidecar_dir, filename)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(assembled.text)


def analyze_file(
    path: str,
    groups_filter: Iterable[str] | None = None,
    drop_trailing_marker: bool = False,
    sidecar_dir: str | None = None,
) -> Iterator[FeatureRecord]:
    piece = load(path, drop_trailing_marker=drop_trailing_marker)
    piece_features = features_base.extract_piece(piece, groups_filter)
    piece_errors = piece_features.pop("_errors", {})

    for part in piece.parts:
        part_features = features_base.extract_part(part, piece, groups_filter)
        errors = {**piece_errors, **part_features.pop("_errors", {})}
        evidence = detect_vocal(part, piece)
        record = FeatureRecord(
            source_path=piece.source_path,
            source_format=piece.source_format,
            part_index=part.index,
            part_name=part.name,
            is_vocal_candidate=evidence.is_candidate,
            vocal_confidence=evidence.confidence,
            # The evidence behind the verdict, not just the verdict: the
            # detector exists to be auditable, and it can only be audited
            # where the user actually looks, which is the output row.
            vocal_signal_lyrics=evidence.signals.get("lyrics"),
            vocal_signal_monophony=_rounded(evidence.signals.get("monophony")),
            vocal_signal_range=_rounded(evidence.signals.get("range")),
            vocal_signal_naming=evidence.signals.get("naming"),
            features={**piece_features, **part_features},
            errors=errors,
        )
        sidecar_name = record.features.get("lyrics_text_path")
        if sidecar_dir and sidecar_name:
            _write_sidecar(part, sidecar_dir, sidecar_name)
        yield record


def run(
    paths: Iterable[str],
    sink: Sink,
    groups_filter: Iterable[str] | None = None,
    drop_trailing_marker: bool = False,
    on_progress=None,
    sidecar_dir: str | None = None,
) -> tuple[int, list[tuple[str, str]]]:
    """Analyse every path into the sink. One bad file never stops the batch.

    ``sidecar_dir``, when given, is where each part's reassembled lyric
    text is written as a ``<stem>.txt`` file alongside the lyric columns
    (see ``_write_sidecar``). ``None`` writes no sidecars at all.
    """
    sink.open(features_base.schema(groups_filter))
    count = 0
    failures: list[tuple[str, str]] = []
    try:
        for path in paths:
            try:
                for record in analyze_file(
                    path, groups_filter, drop_trailing_marker, sidecar_dir
                ):
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

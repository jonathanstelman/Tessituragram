"""load -> prepare -> detect -> extract -> record."""

from __future__ import annotations

import hashlib
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


def _sidecar_target_name(
    filename: str, source_path: str, written: dict[str, str]
) -> str:
    """The name this sidecar is actually written under.

    ``filename`` already carries the part index (``meta.sidecar_name``),
    so two parts of the *same* file never collide. Two *different*
    source files can still land on the same name -- same stem, same
    part index, different directories (``bach/aria.musicxml`` and
    ``handel/aria.musicxml`` both have a part 0) -- which this run-level
    registry is the only place positioned to catch, since a single
    feature call only ever sees one file. On a genuine collision the
    name is disambiguated with a short prefix of the *colliding*
    source's own path hash, so the result is deterministic rather than
    order-dependent.
    """
    owner = written.get(filename)
    if owner is None or owner == source_path:
        written[filename] = source_path
        return filename
    digest = hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:8]
    stem, ext = os.path.splitext(filename)
    disambiguated = f"{stem}.{digest}{ext}"
    written[disambiguated] = source_path
    return disambiguated


def _write_sidecar(part, sidecar_dir: str, filename: str) -> None:
    """Write this part's reassembled lyric text next to the output file.

    A sidecar, not a table cell: a 200-word text is unusable in a CSV
    cell, and the Sheets path caps a cell at 50,000 characters. Nothing
    is written when the part turns out to carry no lyrics after all
    (``assemble_text`` returning ``None``), which should not happen if
    ``filename`` came from a real ``lyrics_text_path`` column, but is
    checked rather than assumed.

    May raise ``OSError`` (an unwritable directory, ``sidecar_dir``
    existing as a plain file, a full disk): the caller is responsible
    for making sure that can never cost the record itself, which is
    already paid for by the time this runs.
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
    sidecar_written: dict[str, str] | None = None,
) -> Iterator[FeatureRecord]:
    """``sidecar_written`` is a run-level registry of sidecar filenames
    already written, keyed to the source path that wrote them --
    shared across every call this run makes, so a same-stem collision
    between two different files is caught (see
    ``_sidecar_target_name``). A fresh, call-local dict (the default)
    only ever sees this one file's own parts, which already carry
    distinct names from their part index and so never collide with
    each other.
    """
    if sidecar_written is None:
        sidecar_written = {}
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
        intended_name = record.features.get("lyrics_text_path")
        if sidecar_dir and intended_name:
            actual_name = _sidecar_target_name(
                intended_name, piece.source_path, sidecar_written
            )
            if actual_name != intended_name:
                # Whatever name is actually written must be exactly what
                # this column records -- a column pointing at a file
                # that was never written (because it was renamed to
                # dodge a collision) is as bad as the collision itself.
                record.features["lyrics_text_path"] = actual_name
            try:
                _write_sidecar(part, sidecar_dir, actual_name)
            except OSError as exc:
                # The classification answers already in `record.features`
                # cost real money to produce. A sidecar write failing --
                # an unwritable directory, a full disk -- must not throw
                # them away with it: surface the failure the same way
                # every other per-record problem is surfaced (the
                # `errors` dict, visible as an `_error_*` column) and
                # still yield the record.
                record.errors["lyrics_sidecar"] = (
                    f"could not write the lyric sidecar {actual_name!r}: "
                    f"{type(exc).__name__}: {exc}"
                )
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
    text is written as a ``<stem>.part<N>.txt`` file alongside the lyric
    columns (see ``_write_sidecar``). ``None`` writes no sidecars at all.
    A single registry of names already written is shared across every
    file in this run, so two different source files that would compute
    the same sidecar name are disambiguated rather than one overwriting
    the other (see ``_sidecar_target_name``).
    """
    sink.open(features_base.schema(groups_filter))
    count = 0
    failures: list[tuple[str, str]] = []
    sidecar_written: dict[str, str] = {}
    try:
        for path in paths:
            try:
                for record in analyze_file(
                    path, groups_filter, drop_trailing_marker,
                    sidecar_dir, sidecar_written,
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

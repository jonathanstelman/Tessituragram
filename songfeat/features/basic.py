"""Surface-level descriptive features.

Deliberately shallow: counts, extremes, and what the notation declares.
Nothing here tries to model difficulty -- these are the fields you would
want in a table before asking any interesting question.
"""

from __future__ import annotations

import statistics
from typing import Any

from music21 import pitch as m21_pitch

from ..model import Part, Piece
from .base import feature


def _note_name(midi: int | None) -> str | None:
    if midi is None:
        return None
    return m21_pitch.Pitch(midi=midi).nameWithOctave


_SHARP_KEYS = ["C", "G", "D", "A", "E", "B", "F#", "C#"]
_FLAT_KEYS = ["C", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"]


def _key_name(sharps: int | None, mode: str | None = None) -> str | None:
    """Tonic implied by a key signature, which is ambiguous without a mode."""
    if sharps is None:
        return None
    if sharps >= 0:
        tonic = _SHARP_KEYS[sharps] if sharps < len(_SHARP_KEYS) else None
    else:
        tonic = _FLAT_KEYS[-sharps] if -sharps < len(_FLAT_KEYS) else None
    if tonic is None:
        return None
    if mode == "minor":
        # Relative minor of the signature's major tonic.
        relative = m21_pitch.Pitch(tonic).transpose(-3)
        return f"{relative.name} minor"
    return f"{tonic} major" if mode == "major" else tonic


@feature(
    name="source",
    group="basic",
    scope="piece",
    source="songfeat",
    description="What the file declared about itself. Where it came from is"
    " an identity column (FeatureRecord.source_path/source_format), not a"
    " feature, so it is not repeated here.",
    fields=("title", "composer"),
)
def source(piece: Piece) -> dict[str, Any]:
    return {
        "title": piece.metadata.get("title"),
        "composer": piece.metadata.get("composer"),
    }


@feature(
    name="size",
    group="basic",
    scope="part",
    source="songfeat",
    description="How much music there is.",
    fields=(
        "n_notes",
        "n_parts",
        "n_measures",
        "quarter_length",
        "duration_seconds",
        "notes_per_second",
    ),
)
def size(part: Part, piece: Piece) -> dict[str, Any]:
    seconds = piece.duration_seconds or 0.0
    n_notes = len(part.notes)
    return {
        "n_notes": n_notes,
        "n_parts": len(piece.parts),
        "n_measures": piece.measure_count,
        "quarter_length": round(piece.quarter_length, 3),
        "duration_seconds": round(seconds, 2) if seconds else None,
        "notes_per_second": round(n_notes / seconds, 3) if seconds else None,
    }


@feature(
    name="pitch_range",
    group="basic",
    scope="part",
    source="songfeat",
    description="Lowest and highest sounding pitches, and central tendency.",
    fields=(
        "min_midi",
        "min_note",
        "max_midi",
        "max_note",
        "range_semitones",
        "mean_midi",
        "median_midi",
    ),
)
def pitch_range(part: Part, piece: Piece) -> dict[str, Any]:
    fields = ("min_midi", "min_note", "max_midi", "max_note",
              "range_semitones", "mean_midi", "median_midi")
    if part.is_empty:
        return dict.fromkeys(fields)
    midis = [n.midi for n in part.notes]
    low, high = min(midis), max(midis)
    return {
        "min_midi": low,
        "min_note": _note_name(low),
        "max_midi": high,
        "max_note": _note_name(high),
        "range_semitones": high - low,
        "mean_midi": round(statistics.fmean(midis), 2),
        "median_midi": round(statistics.median(midis), 1),
    }


@feature(
    name="tempo",
    group="basic",
    scope="piece",
    source="songfeat",
    description="Notated tempo and how much it moves.",
    fields=(
        "tempo_initial_bpm",
        "tempo_min_bpm",
        "tempo_max_bpm",
        "n_tempo_marks",
        "n_tempo_changes",
    ),
)
def tempo(piece: Piece) -> dict[str, Any]:
    if not piece.tempos:
        return {
            "tempo_initial_bpm": None,
            "tempo_min_bpm": None,
            "tempo_max_bpm": None,
            "n_tempo_marks": 0,
            "n_tempo_changes": 0,
        }
    bpms = [t.bpm for t in piece.tempos]
    distinct_consecutive = sum(
        1 for a, b in zip(bpms, bpms[1:]) if round(a, 3) != round(b, 3)
    )
    return {
        "tempo_initial_bpm": round(bpms[0], 2),
        "tempo_min_bpm": round(min(bpms), 2),
        "tempo_max_bpm": round(max(bpms), 2),
        "n_tempo_marks": len(bpms),
        "n_tempo_changes": distinct_consecutive,
    }


@feature(
    name="key_signature",
    group="basic",
    scope="piece",
    source="songfeat",
    description="Key signatures as notated, and how often they change.",
    fields=(
        "key_initial_sharps",
        "key_initial_name",
        "key_initial_mode",
        "n_key_signatures",
        "n_key_changes",
        "key_signatures",
    ),
)
def key_signature(piece: Piece) -> dict[str, Any]:
    if not piece.keys:
        return {
            "key_initial_sharps": None,
            "key_initial_name": None,
            "key_initial_mode": None,
            "n_key_signatures": 0,
            "n_key_changes": 0,
            "key_signatures": None,
        }
    # One score-wide signature often appears once per part; collapse by onset.
    by_onset: dict[float, int] = {}
    for mark in sorted(piece.keys, key=lambda k: k.onset):
        by_onset.setdefault(mark.onset, mark.sharps)
    sharps_sequence = [by_onset[o] for o in sorted(by_onset)]
    changes = sum(1 for a, b in zip(sharps_sequence, sharps_sequence[1:]) if a != b)
    first = piece.keys[0]
    return {
        "key_initial_sharps": first.sharps,
        "key_initial_name": _key_name(first.sharps, first.mode),
        "key_initial_mode": first.mode,
        "n_key_signatures": len(sharps_sequence),
        "n_key_changes": changes,
        "key_signatures": ",".join(str(s) for s in sharps_sequence),
    }


@feature(
    name="analyzed_key",
    group="basic",
    scope="piece",
    source="songfeat",
    description="Key inferred from the notes themselves (Krumhansl-Schmuckler).",
    fields=("analyzed_key", "analyzed_tonic", "analyzed_mode", "is_major", "is_minor",
            "analyzed_key_confidence"),
)
def analyzed_key(piece: Piece) -> dict[str, Any]:
    empty = {
        "analyzed_key": None,
        "analyzed_tonic": None,
        "analyzed_mode": None,
        "is_major": None,
        "is_minor": None,
        "analyzed_key_confidence": None,
    }
    if piece.is_empty or piece.score is None:
        return empty
    found = piece.score.analyze("key")
    mode = found.mode
    return {
        "analyzed_key": str(found),
        "analyzed_tonic": found.tonic.name,
        "analyzed_mode": mode,
        "is_major": mode == "major",
        "is_minor": mode == "minor",
        "analyzed_key_confidence": round(float(found.correlationCoefficient), 3),
    }


@feature(
    name="meter",
    group="basic",
    scope="piece",
    source="songfeat",
    description="Time signatures as notated, and how often they change.",
    fields=("meter_initial", "n_meter_signatures", "n_meter_changes", "meters"),
)
def meter(piece: Piece) -> dict[str, Any]:
    if not piece.meters:
        return {
            "meter_initial": None,
            "n_meter_signatures": 0,
            "n_meter_changes": 0,
            "meters": None,
        }
    by_onset: dict[float, str] = {}
    for mark in sorted(piece.meters, key=lambda m: m.onset):
        by_onset.setdefault(mark.onset, mark.symbol)
    sequence = [by_onset[o] for o in sorted(by_onset)]
    changes = sum(1 for a, b in zip(sequence, sequence[1:]) if a != b)
    return {
        "meter_initial": sequence[0],
        "n_meter_signatures": len(sequence),
        "n_meter_changes": changes,
        "meters": ",".join(sequence),
    }


@feature(
    name="text",
    group="basic",
    scope="part",
    source="songfeat",
    description="Whether the score carries sung text.",
    fields=("has_lyrics", "n_lyric_syllables"),
)
def text(part: Part, piece: Piece) -> dict[str, Any]:
    syllables = sum(1 for n in part.notes if n.lyric)
    return {"has_lyrics": syllables > 0, "n_lyric_syllables": syllables}

"""Parse score files into the normalised :mod:`songfeat.model` objects.

Ingestion goes through music21, so any format it reads is available here
without per-format parsing code. Nothing in this module requires the
trailing C1 reference note that the original Tessituragram CLI expects.
"""

from __future__ import annotations

import os

from music21 import chord as m21_chord
from music21 import converter, instrument, key, meter, stream, tempo

from .model import KeyMark, MeterMark, Note, Part, Piece, Syllable, TempoMark

#: Extensions music21 can read that we advertise support for.
SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".mid": "midi",
    ".midi": "midi",
    ".xml": "musicxml",
    ".musicxml": "musicxml",
    ".mxl": "musicxml",
    ".abc": "abc",
    ".krn": "humdrum",
    ".mei": "mei",
}


class UnsupportedFormatError(ValueError):
    """Raised for a file extension music21 is not expected to read."""


class ParseError(RuntimeError):
    """Raised when music21 fails to parse an otherwise supported file."""


def detect_format(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    try:
        return SUPPORTED_EXTENSIONS[ext]
    except KeyError:
        raise UnsupportedFormatError(
            f"{ext or path!r} is not a supported score format. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        ) from None


DEFAULT_BPM = 120.0


def build_tempo_map(tempos: list[TempoMark]) -> list[tuple[float, float]]:
    """Return sorted (onset_in_quarters, bpm) segments covering the piece.

    MIDI and MusicXML both allow tempo to change mid-piece, so converting
    quarter-note offsets to seconds means walking the segments rather than
    multiplying by a single rate.
    """
    marks = sorted(((t.onset, t.bpm) for t in tempos if t.bpm > 0), key=lambda m: m[0])
    if not marks or marks[0][0] > 0:
        marks.insert(0, (0.0, marks[0][1] if marks else DEFAULT_BPM))
    return marks


def quarters_to_seconds(quarters: float, tempo_map: list[tuple[float, float]]) -> float:
    """Convert an offset in quarter notes to elapsed seconds."""
    if quarters <= 0:
        return 0.0
    total = 0.0
    for index, (start, bpm) in enumerate(tempo_map):
        if start >= quarters:
            break
        end = tempo_map[index + 1][0] if index + 1 < len(tempo_map) else float("inf")
        span = min(end, quarters) - start
        if span > 0:
            total += span * 60.0 / bpm
    return total


def _part_label(part: stream.Part) -> tuple[str | None, str | None]:
    name = part.partName or None
    instrument_name = None
    try:
        found = part.getInstrument(returnDefault=False)
        if found is not None:
            instrument_name = found.instrumentName or None
    except Exception:
        pass
    return name, instrument_name


def _collect_notes(
    parts: list[stream.Part], tempo_map: list[tuple[float, float]]
) -> list[list[Note]]:
    per_part: list[list[Note]] = []
    for index, part in enumerate(parts):
        collected: list[Note] = []
        for element in part.flatten().recurse().notes:
            onset = float(element.offset)
            duration = float(element.duration.quarterLength)
            onset_seconds = quarters_to_seconds(onset, tempo_map)
            duration_seconds = (
                quarters_to_seconds(onset + duration, tempo_map) - onset_seconds
            )
            syllables = tuple(
                Syllable(
                    number=int(getattr(item, "number", 1) or 1),
                    text=item.text,
                    syllabic=getattr(item, "syllabic", None),
                    extend=bool(getattr(item, "extend", False)),
                )
                for item in getattr(element, "lyrics", ())
                if getattr(item, "text", None)
            )
            # Extract lyric for backward compatibility
            lyric = None
            if syllables:
                # Find the lowest-numbered verse (usually verse 1, but may start at 2+)
                lowest_verse = min(syllables, key=lambda s: s.number)
                lyric = lowest_verse.text if lowest_verse else None
            else:
                # Fallback to music21's lyric property only when no syllables
                lyric = getattr(element, "lyric", None) or None
            pitches = (
                element.pitches
                if isinstance(element, m21_chord.Chord)
                else [element.pitch]
            )
            for pitch in pitches:
                collected.append(
                    Note(
                        midi=int(pitch.midi),
                        onset=onset,
                        duration=duration,
                        part=index,
                        onset_seconds=onset_seconds,
                        duration_seconds=duration_seconds,
                        lyric=lyric,
                        is_chord_member=len(pitches) > 1,
                        lyrics=syllables,
                    )
                )
        collected.sort(key=lambda n: (n.onset, n.midi))
        per_part.append(collected)
    return per_part


def _collect_marks(score: stream.Score):
    flat = score.flatten()

    tempos = [
        TempoMark(onset=float(m.offset), bpm=float(m.getQuarterBPM()))
        for m in flat.getElementsByClass(tempo.MetronomeMark)
        if m.getQuarterBPM()
    ]

    keys: list[KeyMark] = []
    for k in flat.getElementsByClass(key.KeySignature):
        mode = getattr(k, "mode", None)
        keys.append(KeyMark(onset=float(k.offset), sharps=int(k.sharps), mode=mode))

    meters = [
        MeterMark(
            onset=float(ts.offset),
            numerator=int(ts.numerator),
            denominator=int(ts.denominator),
        )
        for ts in flat.getElementsByClass(meter.TimeSignature)
    ]

    return tempos, keys, meters


def _measure_count(parts: list[stream.Part]) -> int:
    counts = [len(p.getElementsByClass(stream.Measure)) for p in parts]
    return max(counts) if counts else 0


#: MIDI note number of the C1 reference pitch Tessituragram appends to its
#: corpus files. It is a parsing marker, not music, and skews pitch range.
REFERENCE_MARKER_MIDI = 24


def _drop_trailing_marker(notes: list[Note]) -> tuple[list[Note], Note | None]:
    """Remove a final C1 that is an isolated reference marker.

    Only drops it when it is the last note *and* nothing else in the piece
    sits that low, so genuine bass lines reaching C1 are left alone. Returns
    the dropped marker alongside the survivors (or ``None`` if nothing was
    dropped) so the caller can truncate the piece to the marker's onset —
    discarding its pitch but keeping its time would otherwise read the
    piece as longer than the music.
    """
    if not notes:
        return notes, None
    last = notes[-1]
    if last.midi != REFERENCE_MARKER_MIDI:
        return notes, None
    others = [n for n in notes[:-1] if n.midi <= REFERENCE_MARKER_MIDI]
    if others:
        return notes, None
    return notes[:-1], last


def load(path: str, drop_trailing_marker: bool = False) -> Piece:
    """Parse ``path`` into a :class:`~songfeat.model.Piece`.

    Set ``drop_trailing_marker`` for files from the Tessituragram corpus,
    which append a C1 reference pitch that would otherwise be counted as
    the lowest note of the piece.
    """
    source_format = detect_format(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    try:
        parsed = converter.parse(path)
    except Exception as exc:  # music21 raises a wide variety of errors
        raise ParseError(f"music21 could not parse {path}: {exc}") from exc

    if isinstance(parsed, stream.Opus):
        # music21 returns an Opus for a multi-tune ABC or Humdrum file, and
        # multi-tune is ABC's normal shape. An Opus is not a Score, so the
        # fallback below would wrap the whole collection as a single part:
        # 50 unrelated tunes pooled into one row, with a "compositional
        # range" spanning all of them, a "duration" that is their total, and
        # every tessitura quartile and passaggio dwell averaged across the
        # lot -- confidently, with no error, warning or null.
        #
        # Future work: iterate the opus into one Piece per score, which is
        # the better answer. Refusing is the honest answer until then,
        # because pipeline.run reports and skips a ParseError per the error
        # contract, and a skipped file is recoverable where a pooled row is
        # not.
        raise ParseError(
            f"{path} is a multi-tune file: music21 parsed it as an Opus of "
            f"{len(parsed.scores)} score(s), and songfeat analyses one piece "
            "per file. Pooling them into one record would report a range, "
            "duration and tessitura spanning unrelated pieces. Split the "
            "file into one tune per file. (Analysing each score of an opus "
            "separately is planned but not implemented.)"
        )

    score = parsed if isinstance(parsed, stream.Score) else stream.Score([parsed])
    m21_parts = list(score.parts) or [score]

    tempos, keys, meters = _collect_marks(score)
    tempo_map = build_tempo_map(tempos)
    per_part_notes = _collect_notes(m21_parts, tempo_map)
    parts = []
    dropped_marker_onsets: list[float] = []
    for index, m21_part in enumerate(m21_parts):
        name, instrument_name = (
            _part_label(m21_part) if isinstance(m21_part, stream.Part) else (None, None)
        )
        notes = per_part_notes[index]
        if drop_trailing_marker:
            notes, dropped = _drop_trailing_marker(notes)
            if dropped is not None:
                dropped_marker_onsets.append(dropped.onset)
        parts.append(
            Part(index=index, name=name, instrument=instrument_name, notes=notes)
        )

    quarter_length = float(score.duration.quarterLength) if score.duration else 0.0
    if dropped_marker_onsets:
        # The parsed score still counts a dropped marker's time even though
        # its pitch is gone; truncate to the latest one's onset, never past
        # the parsed extent.
        quarter_length = min(quarter_length, max(dropped_marker_onsets))
    duration_seconds = quarters_to_seconds(quarter_length, tempo_map)

    return Piece(
        source_path=path,
        source_format=source_format,
        parts=parts,
        tempos=tempos,
        keys=keys,
        meters=meters,
        measure_count=_measure_count([p for p in m21_parts if isinstance(p, stream.Part)]),
        quarter_length=quarter_length,
        duration_seconds=duration_seconds,
        metadata={
            "title": (score.metadata.title if score.metadata else None),
            "composer": (score.metadata.composer if score.metadata else None),
        },
        score=score,
    )

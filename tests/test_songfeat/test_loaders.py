import os

import pytest

from songfeat.loaders import (
    DEFAULT_BPM,
    ParseError,
    UnsupportedFormatError,
    build_tempo_map,
    detect_format,
    load,
    quarters_to_seconds,
)
from songfeat.model import Note, TempoMark

ARIA = os.path.join("data", "test_data_arias", "1-I.mid")

ABC_TUNE = """X:1
T:Test Tune
M:4/4
L:1/4
K:G
|:G2 AB|c2 BA|G2 AB|c4:|
"""


def test_detect_format_by_extension():
    assert detect_format("a.mid") == "midi"
    assert detect_format("a.MIDI") == "midi"
    assert detect_format("a.mxl") == "musicxml"
    assert detect_format("a.musicxml") == "musicxml"
    assert detect_format("a.abc") == "abc"


def test_detect_format_rejects_unknown():
    with pytest.raises(UnsupportedFormatError):
        detect_format("song.wav")


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load("does-not-exist.mid")


def test_unparseable_file_raises_parse_error(tmp_path):
    bad = tmp_path / "broken.mid"
    bad.write_bytes(b"this is not a midi file")
    with pytest.raises(ParseError):
        load(str(bad))


def test_load_midi():
    piece = load(ARIA)
    assert piece.source_format == "midi"
    assert len(piece.notes) > 0
    assert piece.measure_count > 0
    assert piece.quarter_length > 0
    assert piece.duration_seconds > 0
    # Notes come back in onset order.
    onsets = [n.onset for n in piece.notes]
    assert onsets == sorted(onsets)


def test_load_abc(tmp_path):
    path = tmp_path / "tune.abc"
    path.write_text(ABC_TUNE)
    piece = load(str(path))
    assert piece.source_format == "abc"
    assert [n.midi for n in piece.notes] == [67, 69, 71, 72, 71, 69, 67, 69, 71, 72]
    assert piece.meters[0].symbol == "4/4"
    assert piece.keys[0].sharps == 1


# --- tempo map -------------------------------------------------------------

def test_tempo_map_defaults_when_no_marks():
    assert build_tempo_map([]) == [(0.0, DEFAULT_BPM)]


def test_tempo_map_backfills_a_late_first_mark():
    mapping = build_tempo_map([TempoMark(onset=8.0, bpm=90.0)])
    assert mapping[0][0] == 0.0


def test_quarters_to_seconds_single_tempo():
    mapping = build_tempo_map([TempoMark(onset=0.0, bpm=120.0)])
    # At 120bpm a quarter note is half a second.
    assert quarters_to_seconds(4, mapping) == pytest.approx(2.0)


def test_quarters_to_seconds_spans_tempo_change():
    mapping = build_tempo_map(
        [TempoMark(onset=0.0, bpm=120.0), TempoMark(onset=4.0, bpm=60.0)]
    )
    # 4 quarters at 120 (2s) then 4 quarters at 60 (4s).
    assert quarters_to_seconds(8, mapping) == pytest.approx(6.0)


def test_quarters_to_seconds_at_zero():
    assert quarters_to_seconds(0, build_tempo_map([])) == 0.0


# --- the Tessituragram C1 reference marker ---------------------------------

def test_marker_is_kept_by_default():
    piece = load(ARIA)
    assert min(n.midi for n in piece.notes) == 24


def test_marker_is_dropped_on_request():
    piece = load(ARIA, drop_trailing_marker=True)
    assert min(n.midi for n in piece.notes) > 24


def test_marker_removal_preserves_genuine_low_notes():
    """A piece that really uses C1 should keep every note."""
    from songfeat.loaders import _drop_trailing_marker

    notes = [
        Note(midi=24, onset=0.0, duration=1.0, part=0),
        Note(midi=60, onset=1.0, duration=1.0, part=0),
        Note(midi=24, onset=2.0, duration=1.0, part=0),
    ]
    survivors, dropped = _drop_trailing_marker(notes)
    assert survivors == notes
    assert dropped is None


def test_marker_removal_on_empty_input():
    from songfeat.loaders import _drop_trailing_marker

    survivors, dropped = _drop_trailing_marker([])
    assert survivors == []
    assert dropped is None


def test_marker_removal_on_marker_only_part():
    """A part that is nothing but the marker must not raise, and reports it."""
    from songfeat.loaders import _drop_trailing_marker

    notes = [Note(midi=24, onset=5.0, duration=1.0, part=0)]
    survivors, dropped = _drop_trailing_marker(notes)
    assert survivors == []
    assert dropped is notes[0]


# --- dropping the marker must also shorten the piece ----------------------
#
# The corpus files all end with a C1 marker whose *time* music21 still
# counts even once _drop_trailing_marker discards its pitch. Reference
# numbers below are measured straight off the spec's ground-truth table for
# aria I (data/test_data_arias/1-I.mid), not derived from our own code.

def test_dropping_marker_truncates_to_marker_onset():
    piece = load(ARIA, drop_trailing_marker=True)
    assert piece.quarter_length == 476.0
    assert piece.duration_seconds == pytest.approx(204.0, abs=0.01)


def test_keeping_marker_leaves_duration_untouched():
    piece = load(ARIA, drop_trailing_marker=False)
    assert piece.quarter_length == 478.0
    assert piece.duration_seconds == pytest.approx(204.857, abs=0.01)


def test_dropping_marker_gives_reference_rest_time():
    piece = load(ARIA, drop_trailing_marker=True)
    sounding = sum(n.duration_seconds for n in piece.notes)
    rest = piece.duration_seconds - sounding
    assert rest == pytest.approx(39.43, abs=0.01)


def test_genuine_trailing_low_c1_leaves_extent_untouched(tmp_path):
    """When another note also sits at or below C1, nothing is dropped, and
    the piece's extent must be left exactly as the parser gave it."""
    from music21 import note as m21_note
    from music21 import stream as m21_stream

    s = m21_stream.Stream()
    s.append(m21_note.Note("C4", quarterLength=1.0))
    s.append(m21_note.Note("C1", quarterLength=1.0))
    s.append(m21_note.Note("C1", quarterLength=1.0))
    out = tmp_path / "genuine_low_c1.musicxml"
    s.write("musicxml", fp=str(out))

    kept = load(str(out), drop_trailing_marker=False)
    dropped = load(str(out), drop_trailing_marker=True)

    assert min(n.midi for n in dropped.notes) == 24
    assert dropped.quarter_length == kept.quarter_length
    assert dropped.duration_seconds == pytest.approx(kept.duration_seconds)


def test_no_marker_leaves_extent_untouched(tmp_path):
    path = tmp_path / "tune.abc"
    path.write_text(ABC_TUNE)

    kept = load(str(path), drop_trailing_marker=False)
    dropped = load(str(path), drop_trailing_marker=True)

    assert dropped.quarter_length == kept.quarter_length
    assert dropped.duration_seconds == pytest.approx(kept.duration_seconds)


def test_multipart_truncates_to_the_later_dropped_marker(tmp_path):
    """Two parts each drop their own marker at a different onset; the piece
    must truncate to whichever onset is later, not to either part alone."""
    from music21 import note as m21_note
    from music21 import stream as m21_stream

    part_a, part_b = m21_stream.Part(), m21_stream.Part()
    for i, midi in enumerate((60, 62, 64)):
        n = m21_note.Note(midi)
        n.quarterLength = 1.0
        part_a.insert(float(i), n)
    marker_a = m21_note.Note(24)
    marker_a.quarterLength = 1.0
    part_a.insert(3.0, marker_a)

    for i, midi in enumerate((55, 57)):
        n = m21_note.Note(midi)
        n.quarterLength = 1.0
        part_b.insert(float(i), n)
    marker_b = m21_note.Note(24)
    marker_b.quarterLength = 1.0
    part_b.insert(6.0, marker_b)

    out = tmp_path / "two_markers.mid"
    m21_stream.Score([part_a, part_b]).write("midi", fp=str(out))

    kept = load(str(out), drop_trailing_marker=False)
    dropped = load(str(out), drop_trailing_marker=True)

    assert kept.quarter_length == 8.0
    assert dropped.quarter_length == 6.0
    # Both parts actually dropped their marker, not just the one that wins.
    assert all(min(p.notes, key=lambda n: n.midi).midi > 24 for p in dropped.parts)


def test_marker_only_part_loads_through_the_full_pipeline(tmp_path):
    """A part that is nothing but the marker must still load without raising,
    collapsing to an empty, zero-length piece."""
    from music21 import note as m21_note
    from music21 import stream as m21_stream

    part = m21_stream.Part()
    marker = m21_note.Note(24)
    marker.quarterLength = 1.0
    part.insert(0.0, marker)

    out = tmp_path / "marker_only.mid"
    m21_stream.Score([part]).write("midi", fp=str(out))

    piece = load(str(out), drop_trailing_marker=True)

    assert piece.notes == []
    assert piece.quarter_length == 0.0
    assert piece.duration_seconds == 0.0


# --- per-part isolation -----------------------------------------------------

def test_multipart_file_keeps_parts_separate(tmp_path):
    from music21 import corpus, converter

    out = tmp_path / "chorale.musicxml"
    converter.parse(corpus.getWork("bach/bwv66.6")).write("musicxml", fp=str(out))
    piece = load(str(out))
    assert len(piece.parts) == 4
    assert all(not p.is_empty for p in piece.parts)
    # Soprano sits above bass; pooling would hide this.
    assert max(n.midi for n in piece.parts[0].notes) > max(
        n.midi for n in piece.parts[3].notes
    )

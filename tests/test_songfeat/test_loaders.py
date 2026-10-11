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
    assert _drop_trailing_marker(notes) == notes


def test_marker_removal_on_empty_input():
    from songfeat.loaders import _drop_trailing_marker

    assert _drop_trailing_marker([]) == []

import os

import pytest

from songfeat.features import extract, groups, registry, schema
from songfeat.features.basic import _key_name, _note_name
from songfeat.model import KeyMark, MeterMark, Note, Part, Piece, TempoMark

ARIA = os.path.join("data", "test_data_arias", "1-I.mid")


def make_piece(**overrides) -> Piece:
    notes = overrides.pop(
        "notes",
        [
            Note(midi=60, onset=0.0, duration=1.0, part=0),
            Note(midi=64, onset=1.0, duration=1.0, part=0),
            Note(midi=67, onset=2.0, duration=2.0, part=0),
        ],
    )
    base = dict(
        source_path="synthetic.mid",
        source_format="midi",
        parts=[Part(index=0, name="Voice", notes=notes)],
        tempos=[TempoMark(onset=0.0, bpm=120.0)],
        keys=[KeyMark(onset=0.0, sharps=0, mode="major")],
        meters=[MeterMark(onset=0.0, numerator=4, denominator=4)],
        measure_count=1,
        quarter_length=4.0,
        duration_seconds=2.0,
    )
    base.update(overrides)
    return Piece(**base)


# --- registry --------------------------------------------------------------

def test_registry_is_populated():
    assert "pitch_range" in registry()
    assert "basic" in groups()


def test_schema_matches_registered_fields():
    names = schema()
    assert "min_note" in names
    assert "n_key_changes" in names
    # No duplicate column names across extractors.
    assert len(names) == len(set(names))


def test_schema_can_filter_by_group():
    assert schema(["basic"]) == schema()
    assert schema(["nonexistent"]) == []


# --- individual features ---------------------------------------------------

def test_pitch_range():
    out = extract(make_piece())
    assert out["min_midi"] == 60
    assert out["min_note"] == "C4"
    assert out["max_note"] == "G4"
    assert out["range_semitones"] == 7


def test_size_counts():
    out = extract(make_piece())
    assert out["n_notes"] == 3
    assert out["n_measures"] == 1
    assert out["notes_per_second"] == pytest.approx(1.5)


def test_meter_and_key_reported():
    out = extract(make_piece())
    assert out["meter_initial"] == "4/4"
    assert out["key_initial_name"] == "C major"
    assert out["n_key_changes"] == 0


def test_key_changes_counted():
    piece = make_piece(
        keys=[
            KeyMark(onset=0.0, sharps=0, mode="major"),
            KeyMark(onset=4.0, sharps=2, mode="major"),
            KeyMark(onset=8.0, sharps=2, mode="major"),
        ]
    )
    out = extract(piece)
    assert out["n_key_signatures"] == 3
    assert out["n_key_changes"] == 1  # 0 -> 2, then 2 -> 2 is not a change


def test_duplicate_key_marks_at_same_offset_are_collapsed():
    """A score-wide signature appears once per part; that is not a change."""
    piece = make_piece(
        keys=[KeyMark(onset=0.0, sharps=3, mode="major") for _ in range(4)]
    )
    out = extract(piece)
    assert out["n_key_signatures"] == 1
    assert out["n_key_changes"] == 0


def test_tempo_changes_counted():
    piece = make_piece(
        tempos=[
            TempoMark(onset=0.0, bpm=120.0),
            TempoMark(onset=4.0, bpm=60.0),
        ]
    )
    out = extract(piece)
    assert out["tempo_initial_bpm"] == 120.0
    assert out["tempo_min_bpm"] == 60.0
    assert out["n_tempo_changes"] == 1


def test_lyrics_detected():
    piece = make_piece(
        notes=[Note(midi=60, onset=0.0, duration=1.0, part=0, lyric="la")]
    )
    out = extract(piece)
    assert out["has_lyrics"] is True
    assert out["n_lyric_syllables"] == 1


def test_empty_piece_yields_nulls_not_errors():
    out = extract(make_piece(notes=[], keys=[], tempos=[], meters=[]))
    assert out["n_notes"] == 0
    assert out["min_note"] is None
    assert out["tempo_initial_bpm"] is None
    assert out["key_initial_name"] is None
    assert out["meter_initial"] is None


def test_a_failing_extractor_does_not_abort_the_record():
    """analyzed_key needs a music21 score; a hand-built Piece has none."""
    out = extract(make_piece())
    assert out["analyzed_key"] is None
    assert out["n_notes"] == 3  # other features still present


# --- helpers ---------------------------------------------------------------

@pytest.mark.parametrize(
    "midi,expected", [(60, "C4"), (24, "C1"), (69, "A4"), (61, "C#4")]
)
def test_note_name(midi, expected):
    assert _note_name(midi) == expected


@pytest.mark.parametrize(
    "sharps,mode,expected",
    [
        (0, "major", "C major"),
        (1, "major", "G major"),
        (-1, "major", "F major"),
        (0, "minor", "A minor"),
        (2, None, "D"),
    ],
)
def test_key_name(sharps, mode, expected):
    assert _key_name(sharps, mode) == expected


# --- integration against a real file ---------------------------------------

def test_real_file_matches_reference_implementation():
    """The original CLI reports D2-E4 for this aria."""
    from songfeat import analyze

    out = analyze(ARIA, drop_trailing_marker=True)
    assert out["min_note"] == "D2"
    assert out["max_note"] == "E4"
    assert out["tempo_initial_bpm"] == 140.0

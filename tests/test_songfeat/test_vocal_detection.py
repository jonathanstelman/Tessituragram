import os
from pathlib import Path

import pytest

from songfeat.loaders import load
from songfeat.model import Note, Part, Piece
from songfeat.vocal import detect_vocal

#: Every file in this directory is a solo vocal aria named "Voice1", with a
#: trailing C1 marker that is a parsing artifact, not music (see loaders.py).
ARIA = os.path.join("data", "test_data_arias", "1-I.mid")


def piece_with(*parts: Part) -> Piece:
    return Piece(source_path="x.mid", source_format="midi", parts=list(parts))


def line(midis, part=0, lyrics=False, instrument=None, name=None) -> Part:
    notes = [
        Note(midi=m, onset=float(i), duration=1.0, part=part,
             duration_seconds=0.5, lyric=("la" if lyrics else None))
        for i, m in enumerate(midis)
    ]
    return Part(index=part, name=name, instrument=instrument, notes=notes)


def test_lyrics_are_strong_evidence():
    part = line([60, 62, 64], lyrics=True)
    assert detect_vocal(part, piece_with(part)).signals["lyrics"] == 1.0


def test_a_sung_line_is_a_candidate():
    part = line([60, 62, 64, 65], lyrics=True, name="Voice")
    evidence = detect_vocal(part, piece_with(part))
    assert evidence.is_candidate is True
    assert evidence.confidence > 0.5


def test_a_chordal_piano_staff_is_not_a_candidate():
    notes = [Note(midi=m, onset=0.0, duration=1.0, part=0, duration_seconds=0.5)
             for m in (48, 52, 55, 60)]
    part = Part(index=0, name="Piano", instrument="Piano", notes=notes)
    evidence = detect_vocal(part, piece_with(part))
    assert evidence.is_candidate is False
    assert evidence.signals["monophony"] < 0.5


def test_a_part_far_outside_vocal_range_scores_low():
    part = line([24, 26, 28], name="Contrabass", instrument="Contrabass")
    assert detect_vocal(part, piece_with(part)).signals["range"] < 0.5


def test_no_part_is_vocal_in_an_instrumental_file():
    """Review Focus 5: a string quartet must not crash or invent a singer."""
    parts = [line([76, 78, 79], part=0, name="Violin I", instrument="Violin"),
             line([69, 71, 72], part=1, name="Violin II", instrument="Violin"),
             line([60, 62, 64], part=2, name="Viola", instrument="Viola"),
             line([40, 42, 43], part=3, name="Cello", instrument="Cello")]
    piece = piece_with(*parts)
    evidence = [detect_vocal(p, piece) for p in parts]
    assert not any(e.is_candidate for e in evidence)
    assert all(0.0 <= e.confidence <= 1.0 for e in evidence)


def test_empty_part_scores_zero_without_raising():
    part = Part(index=0)
    evidence = detect_vocal(part, piece_with(part))
    assert evidence.confidence == 0.0
    assert evidence.is_candidate is False
    assert evidence.signals == {"lyrics": 0.0, "monophony": 0.0, "range": 0.0, "naming": 0.0}


@pytest.mark.parametrize("part_name,expected_naming", [
    # Instrument compounds with voice-type qualifiers (should reject)
    ("Bass Clarinet", 0.0),
    ("Double Bass", 0.0),
    ("Bass Trombone", 0.0),
    ("Bass Flute", 0.0),
    ("Bass Drum", 0.0),
    ("Contrabass", 0.0),
    ("Basset Horn", 0.0),
    ("Alto Saxophone", 0.0),
    ("Alto Flute", 0.0),
    ("Soprano Saxophone", 0.0),
    ("Soprano Recorder", 0.0),
    ("Sopranino Recorder", 0.0),
    ("Soprano Clarinet", 0.0),
    ("Tenor Trombone", 0.0),
    ("Baritone Horn", 0.0),
    ("Baritone Saxophone", 0.0),
    ("Baritone Ukulele", 0.0),
    ("Violin I", 0.0),
    ("Viola", 0.0),
    ("Bass Line", 0.0),
    ("Tenor Line", 0.0),
    # Solo voice-type parts (should accept)
    ("Soprano", 1.0),
    ("Alto", 1.0),
    ("Tenor", 1.0),
    ("Baritone", 1.0),
    ("Bass", 1.0),
    # Voice-type with number decoration (should accept)
    ("Soprano 1", 1.0),
    ("Bass II", 1.0),
    # Voice-type with roman numeral decoration (should accept)
    ("Soprano I", 1.0),
    # Voice-type with word decoration (should accept)
    ("Soprano Solo", 1.0),
    ("Tenor Solo", 1.0),
    ("Bass Solo", 1.0),
    ("Bass Voice", 1.0),
    ("Tenor Voice", 1.0),
    # Multiple voice types (should accept)
    ("Mezzo-Soprano", 1.0),
    # Unambiguous vocal words (should accept)
    ("Voice", 1.0),
    ("Vocal", 1.0),
    ("Vocal Line", 1.0),
    ("Voce", 1.0),
    ("Canto", 1.0),
    ("Sing", 1.0),
    ("Chant", 1.0),
    # Letter/digit-run naming, the corpus's own convention (no separator)
    ("Voice1", 1.0),
    ("Soprano2", 1.0),
    ("Alto1", 1.0),
    ("Bass3", 1.0),
])
def test_naming_signal_specification(part_name, expected_naming):
    """Comprehensive parametrised test of naming signal.

    All voice-type words (soprano, mezzo, alto, tenor, baritone, bass) are ambiguous
    because instrument families use them (Soprano Saxophone, Bass Clarinet, etc.).
    They match only when other tokens are decorations (numbers, roman numerals,
    other voice-type words, or words like solo/voice/vocal/part/line).

    Unambiguous words (voice, vocal, voce, canto, sing, chant) match as whole
    words anywhere in the part name.
    """
    part = line([60, 62, 64], part=0, name=part_name)
    evidence = detect_vocal(part, piece_with(part))
    assert evidence.signals["naming"] == expected_naming, \
        f"{part_name} should have naming={expected_naming} but got {evidence.signals['naming']}"


def test_a_real_aria_is_a_vocal_candidate():
    """The only real input this project has is 150 solo vocal arias, each
    named "Voice1" with no separator before the digit. Every prior round
    tested the negative direction (quartet, instrument names) on real data
    but the positive direction only on hand-built stubs -- which is how a
    100% false-negative rate on the actual corpus survived three reviews.
    """
    piece = load(ARIA, drop_trailing_marker=True)
    evidence = [detect_vocal(p, piece) for p in piece.parts]
    assert any(e.is_candidate for e in evidence)


def test_no_part_is_vocal_in_real_quartet(tmp_path):
    """Review Focus: a real string quartet (Mozart K.155) must not crash or invent a singer."""
    from music21 import corpus

    out = tmp_path / "quartet.musicxml"
    score = corpus.parse("mozart/k155")
    score.write("musicxml", fp=str(out))
    piece = load(str(out))

    # Verify we loaded a quartet
    assert len(piece.parts) == 4

    evidence = [detect_vocal(p, piece) for p in piece.parts]
    assert not any(e.is_candidate for e in evidence)
    assert all(0.0 <= e.confidence <= 1.0 for e in evidence)

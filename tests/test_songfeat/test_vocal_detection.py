from pathlib import Path

from songfeat.loaders import load
from songfeat.model import Note, Part, Piece
from songfeat.vocal import detect_vocal


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


def test_naming_signal_specification():
    """Comprehensive test of naming signal across the specification table.

    Split vocabulary by ambiguity:
    - Unambiguous keywords (voice, vocal, soprano, etc.) match as whole words anywhere
    - Ambiguous keywords (bass, alto, tenor) match only if other tokens are decorations
      (numbers, roman numerals, or words like solo/voice/vocal/part/line)
    """
    # INCORRECT (ambiguous keyword with instrument qualifier)
    part = line([60, 62, 64], part=0, name="Bass Clarinet")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 0.0

    part = line([60, 62, 64], part=0, name="Double Bass")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 0.0

    part = line([60, 62, 64], part=0, name="Bass Trombone")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 0.0

    part = line([60, 62, 64], part=0, name="Alto Saxophone")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 0.0

    # CORRECT (unambiguous keyword alone)
    part = line([60, 62, 64], part=0, name="Soprano")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 1.0

    part = line([60, 62, 64], part=0, name="Bass")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 1.0

    # CORRECT (ambiguous keyword with decoration: number)
    part = line([60, 62, 64], part=0, name="Soprano 1")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 1.0

    # CORRECT (ambiguous keyword with decoration: roman numeral)
    part = line([60, 62, 64], part=0, name="Soprano I")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 1.0

    # CORRECT (ambiguous keyword with decoration word)
    part = line([60, 62, 64], part=0, name="Tenor Solo")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 1.0

    # CORRECT (unambiguous keyword with decoration)
    part = line([60, 62, 64], part=0, name="Vocal Line")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 1.0

    # CORRECT (unambiguous keyword with hyphen)
    part = line([60, 62, 64], part=0, name="Mezzo-Soprano")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 1.0

    # CORRECT (ambiguous keyword with multiple decorations)
    part = line([60, 62, 64], part=0, name="Bass Solo")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 1.0

    # CORRECT (ambiguous keyword with voice decoration)
    part = line([60, 62, 64], part=0, name="Tenor Voice")
    assert detect_vocal(part, piece_with(part)).signals["naming"] == 1.0


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

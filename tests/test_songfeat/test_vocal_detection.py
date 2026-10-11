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

from songfeat.context import PartContext
from songfeat.model import KeyMark, Note, Part, Piece


def part_of(*specs) -> tuple[Part, Piece]:
    """specs are (midi, onset, duration) triples in quarter notes."""
    notes = [
        Note(midi=m, onset=o, duration=d, part=0,
             onset_seconds=o * 0.5, duration_seconds=d * 0.5)
        for m, o, d in specs
    ]
    part = Part(index=0, notes=notes)
    piece = Piece(source_path="x.mid", source_format="midi", parts=[part])
    return part, piece


def test_intervals_are_signed_semitone_steps():
    ctx = PartContext(*part_of((60, 0, 1), (64, 1, 1), (62, 2, 1)))
    assert ctx.intervals == [4, -2]


def test_single_note_part_has_no_intervals():
    """Review Focus 2: no pairs means no intervals, not zero."""
    ctx = PartContext(*part_of((60, 0, 1)))
    assert ctx.intervals == []


def test_empty_part_is_safe():
    part = Part(index=0)
    piece = Piece(source_path="x.mid", source_format="midi", parts=[part])
    ctx = PartContext(part, piece)
    assert ctx.intervals == []
    assert ctx.phrases == []
    assert ctx.is_polyphonic is False


def test_phrases_split_on_rest_gaps():
    # Gap of 2 quarters between note 2 and note 3 exceeds the default threshold.
    ctx = PartContext(*part_of((60, 0, 1), (62, 1, 1), (64, 4, 1), (65, 5, 1)))
    assert [len(p) for p in ctx.phrases] == [2, 2]


def test_a_part_with_no_gaps_is_one_phrase():
    ctx = PartContext(*part_of((60, 0, 1), (62, 1, 1), (64, 2, 1)))
    assert len(ctx.phrases) == 1


def test_polyphonic_part_is_detected_and_reduced():
    """Review Focus 4: chords make melodic intervals ill-defined."""
    ctx = PartContext(*part_of((60, 0, 1), (64, 0, 1), (67, 0, 1), (72, 1, 1)))
    assert ctx.is_polyphonic is True
    # One note per onset: the highest, which is the sung line in a chordal staff.
    assert [n.midi for n in ctx.monophonic] == [67, 72]
    assert ctx.intervals == [5]


def test_prevailing_key_is_the_last_mark_at_or_before_the_onset():
    part, piece = part_of((60, 0, 1), (62, 8, 1))
    piece.keys = [KeyMark(onset=0.0, sharps=0), KeyMark(onset=4.0, sharps=3)]
    ctx = PartContext(part, piece)
    assert ctx.prevailing_key(0.0).sharps == 0
    assert ctx.prevailing_key(8.0).sharps == 3


def test_derivations_are_computed_once():
    ctx = PartContext(*part_of((60, 0, 1), (64, 1, 1)))
    assert ctx.intervals is ctx.intervals

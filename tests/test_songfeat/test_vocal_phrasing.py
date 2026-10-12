import pytest

from songfeat.context import PartContext
from songfeat.features import base
from songfeat.loaders import load
from songfeat.model import Note, Part, Piece


def built(specs, total=None) -> tuple[Part, Piece]:
    """specs are (midi, onset_q, duration_q); seconds assume 120 BPM."""
    notes = [
        Note(midi=m, onset=o, duration=d, part=0,
             onset_seconds=o * 0.5, duration_seconds=d * 0.5)
        for m, o, d in specs
    ]
    part = Part(index=0, notes=notes)
    end = max((n.onset + n.duration for n in notes), default=0.0) * 0.5
    return part, Piece(source_path="x.mid", source_format="midi",
                       parts=[part], duration_seconds=total or end)


def test_phrase_count_matches_rest_structure():
    part, piece = built([(60, 0, 1), (62, 1, 1), (64, 5, 1)])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_phrases"] == 2


def test_longest_phrase_is_measured_in_seconds():
    part, piece = built([(60, 0, 2), (62, 2, 2), (64, 8, 1)])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["phrase_longest_seconds"] == pytest.approx(2.0)


def test_runs_need_enough_consecutive_short_notes():
    # Four 16th notes in a row is a run; two is not.
    short = [(60 + i, i * 0.25, 0.25) for i in range(4)]
    part, piece = built(short)
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_runs"] == 1
    assert out["run_longest_notes"] == 4


def test_long_notes_do_not_form_runs():
    part, piece = built([(60 + i, i * 2.0, 2.0) for i in range(4)])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_runs"] == 0
    assert out["run_note_share"] == 0.0


def test_run_share_is_a_fraction_of_notes():
    specs = [(60 + i, i * 0.25, 0.25) for i in range(4)] + [(72, 4.0, 4.0)]
    part, piece = built(specs)
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["run_note_share"] == pytest.approx(0.8)


def test_single_note_part_has_no_runs_and_one_phrase():
    """Review Focus 2."""
    part, piece = built([(60, 0, 1)])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_phrases"] == 1
    assert out["n_runs"] == 0
    assert out["phrase_mean_seconds"] == pytest.approx(0.5)


def test_empty_part_yields_none():
    part = Part(index=0)
    piece = Piece(source_path="x.mid", source_format="midi", parts=[part])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_phrases"] is None
    assert out["n_runs"] is None


def test_unknown_duration_yields_none_rates_not_zero():
    """A Piece not built by the loader may have no duration_seconds at all.

    runs_per_minute and run_mean_notes_per_second divide by elapsed time;
    an unknown denominator must surface as None, not a fabricated 0.0.
    """
    specs = [(60 + i, i * 0.25, 0.25) for i in range(4)]
    part, piece = built(specs)
    piece.duration_seconds = None
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_runs"] == 1
    assert out["runs_per_minute"] is None


def test_aria_i_phrasing_and_runs_are_musically_plausible():
    """Aria I: 204.0s of mostly-sixteenth coloratura at 140 BPM, 454 notes.

    A real corpus file, not a synthetic gap-free fixture — Task 10 shipped
    a bug that only synthetic fixtures missed.
    """
    piece = load("data/test_data_arias/1-I.mid", drop_trailing_marker=True)
    part = piece.parts[0]
    out = base.extract_part(part, piece, groups_filter=["vocal"])

    assert out["n_phrases"] > 1

    # Phrases are disjoint spans within the piece, so their summed
    # duration cannot exceed the piece's total time.
    context = PartContext(part, piece)
    phrase_seconds_sum = sum(
        (p[-1].onset_seconds or 0.0) + (p[-1].duration_seconds or 0.0)
        - (p[0].onset_seconds or 0.0)
        for p in context.phrases
    )
    assert phrase_seconds_sum <= (piece.duration_seconds or 0.0)

    # Dense sixteenth-note coloratura should register a substantial number
    # of runs, not zero.
    assert out["n_runs"] > 5
    assert out["run_longest_notes"] >= 4

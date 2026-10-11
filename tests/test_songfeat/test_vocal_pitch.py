import pytest

from songfeat.context import PartContext
from songfeat.features import base
from songfeat.features.vocal_pitch import midi_to_hz, weighted_quantile
from songfeat.model import Note, Part, Piece


def built(*specs) -> tuple[Part, Piece]:
    """specs are (midi, duration_seconds) pairs; onsets are sequential."""
    notes = []
    onset = 0.0
    for midi, seconds in specs:
        notes.append(Note(midi=midi, onset=onset, duration=seconds * 2,
                          part=0, onset_seconds=onset * 0.5,
                          duration_seconds=seconds))
        onset += seconds * 2
    part = Part(index=0, notes=notes)
    piece = Piece(source_path="x.mid", source_format="midi", parts=[part],
                  duration_seconds=onset * 0.5)
    return part, piece


def test_midi_to_hz_at_concert_a():
    assert midi_to_hz(69) == pytest.approx(440.0)
    assert midi_to_hz(60) == pytest.approx(261.63, abs=0.01)


def test_weighted_quantile_matches_plain_median_with_equal_weights():
    assert weighted_quantile([1, 2, 3], [1, 1, 1], 0.5) == pytest.approx(2)


def test_weighted_quantile_follows_the_weight():
    # The low value holds almost all the duration, so the median sits there.
    assert weighted_quantile([1, 10], [99, 1], 0.5) == pytest.approx(1)


def test_duration_and_count_weightings_can_disagree():
    """The discrepancy this design exists to expose."""
    part, piece = built((60, 10.0), (72, 1.0), (74, 1.0), (76, 1.0))
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["q2_hz_dur"] < out["q2_hz_cnt"]


def test_extremes_are_unweighted():
    part, piece = built((60, 1.0), (72, 5.0))
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["q0_hz"] == pytest.approx(midi_to_hz(60), abs=0.01)
    assert out["q4_hz"] == pytest.approx(midi_to_hz(72), abs=0.01)


def test_cycle_dose_is_frequency_times_time():
    part, piece = built((69, 2.0))          # 440 Hz for 2 s
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["cycle_dose"] == pytest.approx(880.0, rel=0.001)


def test_rest_ratio_uses_piece_duration():
    part, piece = built((60, 1.0), (62, 1.0))
    piece.duration_seconds = 4.0
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["time_dose_seconds"] == pytest.approx(2.0)
    assert out["rest_seconds"] == pytest.approx(2.0)
    assert out["rest_ratio"] == pytest.approx(0.5)


def test_quartiles_are_ordered():
    part, piece = built((60, 1.0), (64, 1.0), (67, 1.0), (72, 1.0))
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["q0_hz"] <= out["q1_hz_dur"] <= out["q2_hz_dur"] <= out["q3_hz_dur"] <= out["q4_hz"]


def test_empty_part_yields_none():
    part = Part(index=0)
    piece = Piece(source_path="x.mid", source_format="midi", parts=[part])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["q0_hz"] is None
    assert out["cycle_dose"] is None


def test_file_without_a_tempo_mark_still_computes_durations():
    """Review Focus 3: fall back to 120 BPM rather than returning None."""
    from songfeat.loaders import load
    piece = load("data/test_parsing/3 Quarter Notes and Rest.mid")
    out = base.extract_part(piece.parts[0], piece, groups_filter=["vocal"])
    assert out["cycle_dose"] is not None
    assert out["time_dose_seconds"] > 0


# --- Reference values from data/test_data_arias/1-I.mid, measured against
# the ground-truth spreadsheet and the upstream CLI. Duration weighting
# reproduces the spreadsheet's tessitura quartiles exactly; count weighting
# matches neither reference. See the module docstring and the task-9 report
# for the full comparison table.

@pytest.fixture(scope="module")
def aria_i_part():
    from songfeat.loaders import load
    piece = load("data/test_data_arias/1-I.mid", drop_trailing_marker=True)
    return piece.parts[0], piece


def test_aria_i_duration_weighted_quartiles_match_the_spreadsheet(aria_i_part):
    part, piece = aria_i_part
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    # Tight tolerance: these are the rounded reference figures themselves,
    # and our extractor rounds to 2 decimal places the same way.
    assert out["q0_hz"] == pytest.approx(73.42, abs=0.01)
    assert out["q1_hz_dur"] == pytest.approx(130.81, abs=0.01)
    assert out["q2_hz_dur"] == pytest.approx(196.00, abs=0.01)
    assert out["q3_hz_dur"] == pytest.approx(220.00, abs=0.01)
    assert out["q4_hz"] == pytest.approx(329.63, abs=0.01)


def test_aria_i_count_weighted_quartiles_differ_from_duration_weighted(aria_i_part):
    """Pins the discrepancy the design exists to expose: a future change
    that collapses the two weightings to one definition fails this."""
    part, piece = aria_i_part
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["q1_hz_cnt"] == pytest.approx(146.83, abs=0.01)
    assert out["q2_hz_cnt"] == pytest.approx(220.00, abs=0.01)
    assert out["q3_hz_cnt"] == pytest.approx(233.08, abs=0.01)
    assert out["q1_hz_dur"] < out["q1_hz_cnt"]
    assert out["q2_hz_dur"] < out["q2_hz_cnt"]


def test_aria_i_rest_seconds_matches_the_spreadsheet(aria_i_part):
    part, piece = aria_i_part
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    # The spreadsheet's `tr` is 39.43; depends on drop_trailing_marker
    # truncating the piece's extent to 204.0s rather than 204.857s.
    assert out["rest_seconds"] == pytest.approx(39.43, abs=0.01)


def test_aria_i_cycle_dose_matches_the_upstream_cli(aria_i_part):
    part, piece = aria_i_part
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    # The CLI's Fptp is 30702.8; the spreadsheet's figure (30738.44) is a
    # separate, disagreeing reference (see Task 16). Looser tolerance than
    # the quartiles above because this is a sum over 454 notes where
    # float accumulation order can shift the last decimal or two.
    assert out["cycle_dose"] == pytest.approx(30702.8, abs=0.5)


def test_aria_i_quartiles_are_ordered_for_both_weightings(aria_i_part):
    part, piece = aria_i_part
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["q0_hz"] <= out["q1_hz_dur"] <= out["q2_hz_dur"] <= out["q3_hz_dur"] <= out["q4_hz"]
    assert out["q0_hz"] <= out["q1_hz_cnt"] <= out["q2_hz_cnt"] <= out["q3_hz_cnt"] <= out["q4_hz"]


def test_aria_i_dose_and_duration_values_are_non_negative(aria_i_part):
    part, piece = aria_i_part
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["cycle_dose"] >= 0
    assert out["time_dose_seconds"] >= 0
    assert out["rest_seconds"] >= 0
    assert out["sustained_seconds"] >= 0

import pytest

from songfeat.constants import PASSAGGI
from songfeat.features import base
from songfeat.features.vocal_passaggi import PASSAGGI_FIELDS, in_zone, near_zone
from songfeat.model import Note, Part, Piece


def built(*specs) -> tuple[Part, Piece]:
    notes, onset = [], 0.0
    for midi, seconds in specs:
        notes.append(Note(midi=midi, onset=onset, duration=seconds * 2, part=0,
                          onset_seconds=onset * 0.5, duration_seconds=seconds))
        onset += seconds * 2
    part = Part(index=0, notes=notes)
    return part, Piece(source_path="x.mid", source_format="midi",
                       parts=[part], duration_seconds=onset * 0.5)


def built_with_gaps(*specs) -> tuple[Part, Piece]:
    """specs are (midi, duration_seconds, gap_after_seconds) triples.

    Like built(), but each note may be followed by a rest (no Note object,
    just a wider onset step) before the next one — needed to exercise the
    phrase-break path, which built()'s back-to-back notes never trigger.
    Keeps built()'s convention of 2 quarters per second (120bpm), so a
    gap_after_seconds of 1.0 is exactly PHRASE_GAP_QUARTERS (2.0 quarters).
    """
    notes, onset = [], 0.0
    for midi, seconds, gap_after in specs:
        notes.append(Note(midi=midi, onset=onset, duration=seconds * 2, part=0,
                          onset_seconds=onset * 0.5, duration_seconds=seconds))
        onset += seconds * 2 + gap_after * 2
    part = Part(index=0, notes=notes)
    return part, Piece(source_path="x.mid", source_format="midi",
                       parts=[part], duration_seconds=onset * 0.5)


def test_constants_came_from_the_reference_implementation():
    assert PASSAGGI["high"]["middle"] == (311.1, 392.0)
    assert len([r for v in PASSAGGI.values() for r in v]) == 9


def test_in_zone_is_inclusive_of_edges():
    assert in_zone(311.1, (311.1, 392.0)) is True
    assert in_zone(392.0, (311.1, 392.0)) is True
    assert in_zone(300.0, (311.1, 392.0)) is False


def test_near_zone_covers_outside_and_inside_the_edge():
    # Two semitones below 311.1 Hz is about 277 Hz.
    assert near_zone(278.0, (311.1, 392.0)) is True
    assert near_zone(250.0, (311.1, 392.0)) is False


def test_dwell_time_accumulates_per_zone():
    # E4 is 329.63 Hz, inside the high-voice middle passaggio.
    part, piece = built((64, 3.0))
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["pass_high_middle_seconds"] == pytest.approx(3.0)
    assert out["pass_high_middle_pct"] == pytest.approx(100.0)


def test_a_note_outside_every_zone_contributes_nothing():
    part, piece = built((36, 3.0))      # C2, far below every zone
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["pass_high_middle_seconds"] == 0.0


def test_crossings_count_transitions_not_notes():
    # In, out, in again across the high-voice middle zone: two crossings.
    part, piece = built((64, 1.0), (48, 1.0), (64, 1.0))
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["pass_high_crossings"] >= 2


def test_longest_span_is_contiguous_time_inside_a_zone():
    part, piece = built((64, 2.0), (65, 2.0), (48, 1.0), (64, 1.0))
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["pass_high_longest_span_seconds"] == pytest.approx(4.0)


def test_longest_span_breaks_at_a_phrase_gap_even_without_leaving_the_zone():
    """Fix round 1: a rest has no Note object, so a long rest between two
    in-zone stints must still break contiguity — otherwise two 3s spans
    with a breath between score as one unbroken 6s span, overstating how
    hard the passage is (this is a difficulty signal; sitting in a
    passaggio continuously is harder than two shorter stints)."""
    # Two 3s spans inside the high-middle zone (E4), 4s apart -- well past
    # the phrase-gap threshold (PHRASE_GAP_QUARTERS=2.0, i.e. 1s at this
    # tempo), so this does not just confirm "any gap breaks the span".
    part, piece = built_with_gaps((64, 3.0, 4.0), (64, 3.0, 0.0))
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["pass_high_longest_span_seconds"] == pytest.approx(3.0)
    # Total dwell and crossings were already correct; the fix must not
    # change them. No note is ever outside the zone, so no crossing.
    assert out["pass_high_middle_seconds"] == pytest.approx(6.0)
    assert out["pass_high_crossings"] == 0


def test_longest_span_joins_across_a_gap_below_the_phrase_threshold():
    """A gap below PHRASE_GAP_QUARTERS is not a phrase break -- reusing
    PartContext.phrases' own threshold (not a smaller local epsilon) means
    a short breath still joins into one contiguous span."""
    # 0.5s gap -> 1.0 quarter at this tempo, below the 2.0-quarter threshold.
    part, piece = built_with_gaps((64, 3.0, 0.5), (64, 3.0, 0.0))
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["pass_high_longest_span_seconds"] == pytest.approx(6.0)
    assert out["pass_high_middle_seconds"] == pytest.approx(6.0)
    assert out["pass_high_crossings"] == 0


def test_empty_part_yields_none_for_every_field():
    part = Part(index=0)
    piece = Piece(source_path="x.mid", source_format="midi", parts=[part])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert all(out[f] is None for f in PASSAGGI_FIELDS)


# --- Ground truth from data/test_data_arias/1-I.mid, measured against the
# project's reference spreadsheet (tests/system_tests/Master Data
# Calculation.xlsx, sheet I). The reference implementation at
# src/tessitura.py:70 uses a +/-0.1 Hz tolerance on zone edges, because
# every edge is an equal-tempered frequency rounded to one decimal and a
# strict comparison silently drops the note sitting on the true boundary
# (see docs/superpowers/sdd task-10 ruling H). Tolerance here is 0.2s:
# tight enough to catch a real error, loose enough for the ~0.1-0.15s
# residual gap against the spreadsheet that neither strict nor tolerant
# comparison fully closes.

@pytest.fixture(scope="module")
def aria_i_part():
    from songfeat.loaders import load
    piece = load("data/test_data_arias/1-I.mid", drop_trailing_marker=True)
    return piece.parts[0], piece


def test_aria_i_passaggio_dwell_times_match_the_spreadsheet(aria_i_part):
    part, piece = aria_i_part
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["pass_low_middle_seconds"] == pytest.approx(25.607, abs=0.2)
    assert out["pass_low_low_seconds"] == pytest.approx(59.179, abs=0.2)
    assert out["pass_medium_middle_seconds"] == pytest.approx(21.321, abs=0.2)
    assert out["pass_medium_low_seconds"] == pytest.approx(56.071, abs=0.2)
    assert out["pass_high_middle_seconds"] == pytest.approx(0.679, abs=0.2)
    assert out["pass_high_low_seconds"] == pytest.approx(34.929, abs=0.2)


def test_aria_i_passaggio_percentages_sum_within_each_voice(aria_i_part):
    """The three registers of a single voice type are disjoint zones, so
    their percentages must sum to no more than 100% of sounding time."""
    part, piece = aria_i_part
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    for voice in ("high", "medium", "low"):
        total = sum(
            out[f"pass_{voice}_{register}_pct"]
            for register in ("high", "middle", "low")
        )
        assert 0.0 <= total <= 100.0 + 0.01


# --- Fix round 3: dwell percentages and spans are wall-clock quantities ----
#
# `pass_*_seconds` stays a duration sum (a cumulative dwell dose, pinned
# above against the spreadsheet). The percentage and the longest span are
# wall-clock readings, so both are measured against the union of sounding
# intervals; on a monophonic line, which the whole corpus is, union and
# sum coincide and nothing above moves.

def chordal(total_seconds: float, *events) -> tuple[Part, Piece]:
    """events are (onset_seconds, duration_seconds, midi...) tuples."""
    notes = []
    for onset, seconds, *pitches in events:
        for midi in pitches:
            notes.append(Note(
                midi=midi, onset=onset * 2, duration=seconds * 2, part=0,
                onset_seconds=onset, duration_seconds=seconds,
                is_chord_member=len(pitches) > 1,
            ))
    part = Part(index=0, notes=notes)
    return part, Piece(source_path="x.mid", source_format="midi",
                       parts=[part], duration_seconds=total_seconds)


def test_longest_span_cannot_outlast_the_piece():
    """A chord repeated through the piece: the old accumulator summed every
    chord member's duration, so ten seconds of music reported a 40-second
    continuous span inside a zone."""
    chords = [(float(i), 1.0, 72, 73, 74, 76) for i in range(10)]
    part, piece = chordal(10.0, *chords)
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["pass_low_high_seconds"] == pytest.approx(40.0)
    assert out["pass_low_longest_span_seconds"] == pytest.approx(10.0)
    assert out["pass_low_longest_span_seconds"] <= piece.duration_seconds


def test_dwell_percentage_is_a_share_of_wall_clock_sounding_time():
    """One second of in-zone chord, then one second out of zone.

    The singer is in the zone for half the time they are sounding. The
    old denominator (the duration sum, 5.0 s) and the old numerator (4.0 s
    of chord-member duration) together reported 80%.
    """
    part, piece = chordal(10.0, (0.0, 1.0, 72, 73, 74, 76), (1.0, 1.0, 67))
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["pass_low_high_seconds"] == pytest.approx(4.0)
    assert out["pass_low_high_pct"] == pytest.approx(50.0)


def test_percentage_and_span_are_unchanged_on_a_monophonic_line():
    """Union equals sum with no overlap, so the corpus values must not
    move -- otherwise this fix would be a silent recalibration."""
    part, piece = built((72, 1.0), (73, 1.0), (67, 2.0))
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["pass_low_high_seconds"] == pytest.approx(2.0)
    assert out["pass_low_high_pct"] == pytest.approx(50.0)
    assert out["pass_low_longest_span_seconds"] == pytest.approx(2.0)

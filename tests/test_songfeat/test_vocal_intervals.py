import pytest

from songfeat.features import base
from songfeat.model import KeyMark, Note, Part, Piece


def built(midis, keys=None) -> tuple[Part, Piece]:
    notes = [
        Note(midi=m, onset=float(i), duration=1.0, part=0,
             onset_seconds=i * 0.5, duration_seconds=0.5)
        for i, m in enumerate(midis)
    ]
    part = Part(index=0, notes=notes)
    piece = Piece(source_path="x.mid", source_format="midi", parts=[part],
                  duration_seconds=len(midis) * 0.5,
                  keys=keys or [KeyMark(onset=0.0, sharps=0, mode="major")])
    return part, piece


def test_max_leap_is_absolute():
    part, piece = built([60, 72, 60])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["leap_max_semitones"] == 12


def test_leap_shares_use_thresholds():
    part, piece = built([60, 62, 67, 60])     # +2, +5, -7
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["leap_share_gt2"] == pytest.approx(2 / 3)
    assert out["leap_share_gt4"] == pytest.approx(2 / 3)


def test_leaps_over_an_octave_are_counted():
    part, piece = built([60, 74])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_leaps_over_octave"] == 1


def test_consecutive_leaps_without_recovery():
    part, piece = built([60, 67, 74])         # two leaps in a row
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_consecutive_leaps"] == 1


def test_unprepared_leap_is_one_not_resolved_by_contrary_step():
    # Leap up a fifth then continue up by step: unresolved.
    part, piece = built([60, 67, 69])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_unprepared_leaps"] == 1
    # Leap up a fifth then step back down: resolved.
    part, piece = built([60, 67, 65])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_unprepared_leaps"] == 0


def test_ascending_share_distinguishes_direction():
    part, piece = built([60, 67, 60, 67])     # up, down, up
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["leap_ascending_share"] == pytest.approx(2 / 3)


def test_nondiatonic_share_uses_the_prevailing_key():
    # C major: C D E F# -> one note outside the scale.
    part, piece = built([60, 62, 64, 66])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["nondiatonic_share"] == pytest.approx(0.25)


def test_key_change_moves_the_diatonic_reference():
    keys = [KeyMark(onset=0.0, sharps=0, mode="major"),
            KeyMark(onset=2.0, sharps=6, mode="major")]
    part, piece = built([60, 62, 66, 68], keys=keys)
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    # F# and G# are diatonic in F# major, so fewer than half are outside.
    assert out["nondiatonic_share"] < 0.5


def test_longest_chromatic_run():
    part, piece = built([60, 61, 62, 63, 67])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["chromatic_run_longest"] == 4


def test_single_note_part_has_no_interval_features():
    """Review Focus 2: no pairs means None, never 0.0."""
    part, piece = built([60])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["leap_max_semitones"] is None
    assert out["leap_share_gt2"] is None
    assert out["interval_mean_abs"] is None
    # Pitch-class features need only one note and must still compute.
    assert out["n_distinct_pitch_classes"] == 1


def test_empty_part_yields_none():
    part = Part(index=0)
    piece = Piece(source_path="x.mid", source_format="midi", parts=[part])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["leap_max_semitones"] is None
    assert out["nondiatonic_share"] is None


def test_leaps_into_extremes_counts_landings_in_the_parts_own_outer_decile():
    # Range 60-72 (span 12): extremes are <=61.2 or >=70.8. Both leaps land
    # on the part's own min/max, so both count.
    part, piece = built([60, 72, 61])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_leaps_into_extremes"] == 2


def test_leaps_into_extremes_is_zero_when_no_leap_lands_there():
    # Range 60-70 (span 10): extremes are <=61.0 or >=69.0, but the only
    # leap (62->65) lands well inside the middle 80%. The actual min (60)
    # and max (70) are reached by step, not by a leap landing.
    part, piece = built([60, 62, 65, 64, 66, 68, 70])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_leaps_into_extremes"] == 0


def test_zone_crossing_uses_in_zones_shared_edge_tolerance():
    """D4's true frequency (293.6648 Hz) sits 0.0352 Hz below the
    medium/middle zone's lower edge (293.7 Hz) -- the same boundary note
    responsible for Ruling H's dwell-time error in vocal_passaggi.
    in_zone includes it via a +-0.1 Hz tolerance; the overlap check this
    feature uses must agree, not re-derive its own stricter comparison.
    """
    from songfeat.features.vocal_passaggi import in_zone, zone_overlaps
    from songfeat.features.vocal_pitch import midi_to_hz

    d4_hz = midi_to_hz(62)
    zone = (293.7, 370.0)
    assert in_zone(d4_hz, zone) is True
    assert zone_overlaps(d4_hz, d4_hz, zone) is True
    # The open-coded strict comparison this feature used to use would have
    # missed D4 entirely, on this zone in isolation.
    assert not (d4_hz < zone[1] and d4_hz > zone[0])


def test_leap_landing_on_d4_counts_as_crossing_a_passaggio_zone():
    # A3 -> D4: lands on the medium/middle zone's tolerance-only edge.
    # (This particular leap also overlaps an adjacent zone outright, so it
    # was already counted before the shared-tolerance fix -- the case
    # below isolates the fix instead.)
    part, piece = built([57, 62])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_leaps_crossing_passaggio"] == 1


def test_leap_crossing_is_detected_only_through_the_shared_tolerance():
    """A4 (440 Hz) to C5 (523.2511 Hz) sits entirely in the gap between
    the passaggio bands (392-523.3 Hz) except that C5's true frequency is
    0.049 Hz below the low/high zone's lower edge (523.3 Hz) -- inside
    only via the same tolerance in_zone applies. No other zone touches
    this leap, so this case flips cleanly: before sharing in_zone's
    tolerance via zone_overlaps, this was n_leaps_crossing_passaggio == 0;
    after, it is 1.
    """
    part, piece = built([69, 72])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_leaps_crossing_passaggio"] == 1


def test_no_leaps_gives_none_ascending_share_but_real_zero_shares():
    """leap_ascending_share divides by the *leap* count, which is zero here
    -- undefined, not a measured "0% ascend". The gt2/gt4/gt7 shares divide
    by the *interval* count, which is non-empty, so those stay real 0.0s,
    and n_leaps_over_octave is a real 0 leap count. All-stepwise motion:
    +2, +2, -2, -2.
    """
    part, piece = built([60, 62, 64, 62, 60])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["leap_ascending_share"] is None
    assert out["leap_share_gt2"] == 0.0
    assert out["leap_share_gt4"] == 0.0
    assert out["leap_share_gt7"] == 0.0
    assert out["n_leaps_over_octave"] == 0


# --- Reference values from data/test_data_arias/1-I.mid: a D-major
# coloratura aria (analysed key "D major", 0.718 confidence, 2 sharps
# notated), 454 notes spanning D2-E4 (MIDI 38-64). See the task-12 report
# for the plausibility discussion behind each figure, including the count
# of non-diatonic pitch classes, which is higher than a "diatonic D major"
# label alone would suggest because of chromatic neighbour/passing tones
# in the ornamentation.

def test_aria_i_leap_and_chromaticism_values_are_musically_plausible():
    from songfeat.loaders import load

    piece = load("data/test_data_arias/1-I.mid", drop_trailing_marker=True)
    part = piece.parts[0]
    out = base.extract_part(part, piece, groups_filter=["vocal"])

    # Max leap of two octaves (D2 to D4) is a real, if extreme, interval
    # within the part's own D2-E4 span -- not a bug in this extractor.
    assert out["leap_max_semitones"] == 24
    # Mostly stepwise/small-interval coloratura motion, averaging close to
    # a major third.
    assert out["interval_mean_abs"] == pytest.approx(3.011, abs=0.001)
    # D major has 2 sharps; most of the line stays inside that collection.
    assert out["nondiatonic_share"] == pytest.approx(0.1278, abs=0.0001)
    # High but sub-maximal uncertainty: usage leans on the 7 diatonic
    # classes (max possible here is log2(7) =~ 2.807) with a modest
    # amount of chromatic colour on top.
    assert out["pitch_class_entropy"] == pytest.approx(2.7665, abs=0.001)
    # 11 of 12 pitch classes appear (only D# is absent) -- more than a
    # "diatonic D major" label implies, but consistent with chromatic
    # appoggiaturas/neighbour tones typical of coloratura ornamentation,
    # confirmed by how thinly those extra classes are used (58/454 notes,
    # matching nondiatonic_share exactly).
    assert out["n_distinct_pitch_classes"] == 11

import pytest

from songfeat.profile import correlated_pairs, profile_records, weak_for_format
from songfeat.record import FeatureRecord


def record(**features) -> FeatureRecord:
    return FeatureRecord(
        source_path="x.mid", source_format="midi", part_index=0,
        features=features,
    )


def test_constant_column_is_flagged():
    records = [record(a=1.0, b=float(i)) for i in range(5)]
    by_name = {p.name: p for p in profile_records(records)}
    assert by_name["a"].is_constant is True
    assert by_name["b"].is_constant is False


def test_null_rate_is_reported():
    records = [record(a=1.0), record(a=None), record(a=None), record(a=2.0)]
    by_name = {p.name: p for p in profile_records(records)}
    assert by_name["a"].null_rate == pytest.approx(0.5)


def test_all_null_column_is_constant_and_fully_null():
    records = [record(a=None) for _ in range(3)]
    by_name = {p.name: p for p in profile_records(records)}
    assert by_name["a"].null_rate == 1.0
    assert by_name["a"].is_constant is True
    assert by_name["a"].variance is None


def test_variance_is_computed_for_numeric_columns():
    records = [record(a=float(i)) for i in range(4)]
    by_name = {p.name: p for p in profile_records(records)}
    # Sample variance of 0,1,2,3 is 5/3. Pin the value: "> 0" would pass
    # for any positive number, including a wrong one.
    assert by_name["a"].variance == pytest.approx(5 / 3)


def test_string_columns_report_distinct_counts_not_variance():
    records = [record(a="C4"), record(a="D4"), record(a="C4")]
    by_name = {p.name: p for p in profile_records(records)}
    assert by_name["a"].n_distinct == 2
    assert by_name["a"].variance is None


def test_perfectly_correlated_columns_are_found():
    records = [record(a=float(i), b=float(i) * 2) for i in range(6)]
    pairs = correlated_pairs(records, threshold=0.95)
    assert ("a", "b", pytest.approx(1.0, abs=0.001)) in [
        (x, y, r) for x, y, r in pairs
    ]


def test_uncorrelated_columns_are_not_reported():
    records = [record(a=1.0, b=0.0), record(a=2.0, b=5.0), record(a=3.0, b=1.0)]
    # Assert the result is empty outright rather than "nothing above 0.99":
    # the latter also passes if the function always returns nothing.
    assert correlated_pairs(records, 0.99) == []
    # And confirm it is live on this same data at a threshold it should meet,
    # so the emptiness above is a real verdict and not a dead code path.
    assert correlated_pairs(records, 0.1), "function returned nothing at any threshold"


def test_empty_input_is_safe():
    assert profile_records([]) == []
    assert correlated_pairs([]) == []


def test_weak_for_format_flags_chromaticism_on_midi():
    # chromaticism (Task 12), lyrics_text (Task 2 of the lyrics plan),
    # lyrics_provenance (Task 11), lyrics_themes (Task 5), lyrics_tone
    # and lyrics_advisories (both Task 6), lyrics_perspective (Task 7),
    # and lyrics_sensitive and lyrics_age (both Task 8) are the features
    # with best_with set, and all exclude midi -- pin the exact field
    # names, not just "non-empty", so a future best_with change on a
    # different feature is caught too.
    from songfeat.features.lyrics.themes import THEME_FIELDS
    from songfeat.features.lyrics.tone import TONE_FIELDS
    from songfeat.features.lyrics.advisories import ADVISORY_FIELDS
    from songfeat.features.lyrics.perspective import PERSPECTIVE_FIELDS
    from songfeat.features.lyrics.sensitive import SENSITIVE_FIELDS
    from songfeat.features.lyrics.age import AGE_FIELDS
    from songfeat.features.lyrics.meta import PROVENANCE_FIELDS

    weak = weak_for_format("midi")
    assert weak == {
        "nondiatonic_share", "chromatic_run_longest",
        "pitch_class_entropy", "n_distinct_pitch_classes",
        "lyrics_word_count", "lyrics_verse_count", "lyrics_sha256",
        "lyrics_text_path", "lyrics_undefined_reason",
    } | set(THEME_FIELDS) | set(TONE_FIELDS) | set(ADVISORY_FIELDS) | set(PERSPECTIVE_FIELDS) | set(SENSITIVE_FIELDS) | set(AGE_FIELDS) | set(PROVENANCE_FIELDS)
    # A feature with best_with=None (the default -- "equally valid for
    # every format") must never be flagged, on any format.
    assert "leap_max_semitones" not in weak

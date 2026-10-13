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


def test_correlated_pairs_compares_the_rows_where_both_columns_are_known():
    """A column with one null used to be dropped entirely. With the
    lyrics group that is every column on every MIDI file, so the
    profiler would under-report redundancy precisely where it is
    likeliest."""
    from songfeat.profile import correlated_pairs

    records = [
        {"a": 1.0, "b": 2.0, "c": None},
        {"a": 2.0, "b": 4.0, "c": 1.0},
        {"a": 3.0, "b": 6.0, "c": 2.0},
        {"a": 4.0, "b": 8.0, "c": 3.0},
    ]
    pairs = dict(((x, y), r) for x, y, r in correlated_pairs(records, 0.99))
    assert pairs[("a", "b")] == pytest.approx(1.0), "perfectly collinear"
    assert pairs[("a", "c")] == pytest.approx(1.0), (
        "also collinear over the three rows where both are known; the old "
        "implementation dropped c for having one null"
    )


def test_a_column_with_too_few_known_rows_is_reported_as_unassessable():
    """Not silently dropped: 'we could not tell' is different from
    'not redundant'."""
    from songfeat.profile import correlated_pairs, unassessable_columns

    records = [
        {"a": 1.0, "b": 1.0, "d": None},
        {"a": 2.0, "b": 2.0, "d": None},
        {"a": 3.0, "b": 3.0, "d": 7.0},
    ]
    assert "d" in unassessable_columns(records)
    assert all("d" not in pair for pair in correlated_pairs(records, 0.99))


def test_print_profile_distinguishes_unassessable_from_assessed_columns(capsys):
    """``--profile`` must say "too few known values to assess" for a column
    with fewer than MIN_PAIRWISE known rows, not leave it looking merely
    uncorrelated -- and must still report a pair that does have enough rows
    as correlated, so the two outputs stay distinguishable rather than both
    just being silence."""
    from songfeat.cli import print_profile

    records = [
        record(a=1.0, b=2.0, d=None),
        record(a=2.0, b=4.0, d=None),
        record(a=3.0, b=6.0, d=7.0),
    ]
    print_profile(records)
    out = capsys.readouterr().out

    before_unassessable, _, unassessable_block = out.partition(
        "columns have too few known values to assess for redundancy:\n"
    )
    _, _, pairs_block = before_unassessable.partition("correlated pairs at |r| >= 0.95:\n")

    # Exactly one correlated pair reported, and it is (a, b) -- the pair
    # with all three rows known -- not "d", which has only one.
    pair_lines = [line for line in pairs_block.splitlines() if line.startswith("  ")]
    assert len(pair_lines) == 1
    assert pair_lines[0].split()[:2] == ["a", "b"]

    # "d" is named as unassessable, on its own line, and nothing else is.
    assert unassessable_block.strip() == "d"


def test_unassessable_columns_ignores_fully_populated_string_columns():
    """A fully-populated string column (e.g. clf_model) is not a candidate
    for redundancy assessment at all -- unlike a genuinely sparse numeric
    column, it must never appear under "too few known values to assess."
    This is the regression guard for the defect where counting any
    non-numeric value as "not known" reported every string column as
    unmeasurable on every corpus."""
    from songfeat.profile import unassessable_columns

    records = [
        {"txt": "a", "sparse": None},
        {"txt": "b", "sparse": None},
        {"txt": "c", "sparse": 7.0},
    ]
    assert unassessable_columns(records) == ["sparse"]


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


def test_unassessable_columns_accepts_a_feature_record_like_its_sibling():
    """``_as_mapping``'s docstring promises both functions take either a
    FeatureRecord or a plain dict, but this one called ``record.items()``
    and so raised on a real record. The two functions already disagreed
    once about what "assessable" means; they now share one predicate,
    and they must also share one view of what a record is."""
    from songfeat.profile import correlated_pairs, unassessable_columns
    from songfeat.record import FeatureRecord

    records = [
        FeatureRecord(source_path=f"/tmp/{index}.mid", source_format="midi",
                      part_index=0,
                      features={"dense": float(index), "sparse": None,
                                "name": "a string"})
        for index in range(4)
    ]
    # dense has four known values; sparse has none; name is not numeric
    # and so is not a candidate at all.
    assert unassessable_columns(records) == ["sparse"]
    # And the shared predicate means the pair-wise half agrees: it, too,
    # considers only dense and sparse, so no pair survives.
    assert correlated_pairs(records) == []


def test_the_two_functions_share_one_eligibility_predicate():
    """Identical copies of a rule are the state immediately before they
    diverge again. One predicate, called by both."""
    from songfeat import profile

    assert profile._assessable([1, 2.5, None]) is True
    assert profile._assessable([1, "two"]) is False
    assert profile._assessable([True, 1]) is False, (
        "bool is deliberately excluded even though it is an int subclass"
    )
    assert profile._assessable([]) is True, (
        "a column with no rows is vacuously numeric; the row count is "
        "what unassessable_columns then reports on"
    )

import pytest

from songfeat.profile import correlated_pairs, profile_records
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

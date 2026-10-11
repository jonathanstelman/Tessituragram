"""Invariants that hold whatever the feature definitions turn out to be.

Every test here loops over the corpus sample, so an empty or partially
loaded sample would make the whole file pass while asserting nothing.
`test_the_sample_loaded` exists to make that failure loud, and the
filtered tests count what they checked for the same reason.
"""

import os

import pytest

from songfeat.pipeline import analyze_file

CORPUS = os.path.join("data", "test_data_arias")
SAMPLE = [os.path.join(CORPUS, n) for n in sorted(os.listdir(CORPUS))[:12]]

#: Borrowed music21 extractors that fail on a reconstructed single part.
#: Imported from the adapter's own test module so the two cannot drift.
from tests.test_songfeat.test_pipeline import EXPECTED_BORROWED_FAILURES


@pytest.fixture(scope="module")
def records():
    out = []
    for path in SAMPLE:
        out.extend(analyze_file(path, drop_trailing_marker=True))
    return out


def test_the_sample_loaded(records):
    """Guards every other test in this file.

    All of them iterate `records`; an empty list would make each one pass
    vacuously. The corpus files are single-part, so one record per file.
    """
    assert len(SAMPLE) == 12, SAMPLE
    assert len(records) == len(SAMPLE), [r.source_path for r in records]


def _checked(values):
    """Assert a filtered test actually found something, then return it."""
    assert values, "filter matched no columns; the test would assert nothing"
    return values


def test_quartiles_are_ordered(records):
    for record in records:
        f = record.features
        ordered = [f["q0_hz"], f["q1_hz_dur"], f["q2_hz_dur"], f["q3_hz_dur"], f["q4_hz"]]
        # Duration-weighted quartiles are None on a part with no sounding
        # time; the extremes stay real. Skip rather than crash on sorted().
        if any(v is None for v in ordered):
            continue
        assert ordered == sorted(ordered), record.source_path


def test_count_weighted_quartiles_are_also_ordered(records):
    for record in records:
        f = record.features
        trio = [f["q1_hz_cnt"], f["q2_hz_cnt"], f["q3_hz_cnt"]]
        if any(v is None for v in trio):
            continue
        assert trio[0] <= trio[1] <= trio[2], record.source_path


def test_durations_are_non_negative(records):
    seen = 0
    for record in records:
        for field in ("cycle_dose", "time_dose_seconds", "rest_seconds"):
            value = record.features[field]
            if value is None:        # rest_seconds is None when total time is unknown
                continue
            seen += 1
            assert value >= 0, (record.source_path, field)
    assert seen, "no duration values were checked"


def test_rest_ratio_is_a_proportion(records):
    seen = 0
    for record in records:
        value = record.features["rest_ratio"]
        if value is None:
            continue
        seen += 1
        assert 0.0 <= value <= 1.0, record.source_path
    assert seen, "no rest_ratio values were checked"


def test_passaggio_percentages_never_exceed_one_hundred(records):
    checked = _checked([
        (r.source_path, name, value)
        for r in records
        for name, value in r.features.items()
        if name.endswith("_pct") and value is not None
    ])
    for path, name, value in checked:
        assert 0.0 <= value <= 100.0, (path, name)


def test_phrase_time_does_not_exceed_total_time(records):
    seen = 0
    for record in records:
        longest = record.features["phrase_longest_seconds"]
        sounding = record.features["time_dose_seconds"]
        rest = record.features["rest_seconds"]
        if None in (longest, sounding, rest):
            continue
        seen += 1
        assert longest <= sounding + rest + 0.01, record.source_path
    assert seen, "no phrase durations were checked"


def test_shares_are_proportions(records):
    checked = _checked([
        (r.source_path, name, value)
        for r in records
        for name, value in r.features.items()
        if name.endswith("_share") and value is not None
    ])
    for path, name, value in checked:
        assert 0.0 <= value <= 1.0, (path, name)


def test_only_the_known_borrowed_features_error(records):
    """The error set is pinned, not asserted empty.

    Roughly a dozen jSymbolic and native extractors are unimplemented in
    music21 or meaningless on a reconstructed single part. Asserting zero
    errors would fail; asserting equality catches a NEW failure appearing
    or a known one silently disappearing.
    """
    failed = {name for r in records for name in r.errors}
    assert failed == EXPECTED_BORROWED_FAILURES, {
        "unexpected": sorted(failed - EXPECTED_BORROWED_FAILURES),
        "no longer failing": sorted(EXPECTED_BORROWED_FAILURES - failed),
    }


def test_every_record_has_the_full_schema(records):
    from songfeat.features import base
    expected = set(base.schema()) - set(type(records[0]).IDENTITY)
    assert expected, "schema minus identity columns was empty"
    for record in records:
        assert expected <= set(record.features), record.source_path

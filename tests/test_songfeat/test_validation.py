import os

import pytest

from songfeat.validation import GROUND_TRUTH_LABELS, compare, load_ground_truth

XLSX = os.path.join("tests", "system_tests", "Master Data Calculation.xlsx")
CORPUS = os.path.join("data", "test_data_arias")


def test_ground_truth_loads_every_aria():
    truth = load_ground_truth(XLSX)
    assert len(truth) == 150
    assert "I" in truth


def test_known_values_for_aria_one():
    """Values read off the sheet by hand while writing the spec."""
    aria = load_ground_truth(XLSX)["I"]
    assert aria["t"] == pytest.approx(204.0, abs=0.01)
    assert aria["tr"] == pytest.approx(39.43, abs=0.01)
    assert aria["Q0p"] == pytest.approx(73.42, abs=0.01)
    assert aria["Q4p"] == pytest.approx(329.63, abs=0.01)
    assert aria["Q1p"] == pytest.approx(130.81, abs=0.01)
    assert aria["Q2p"] == pytest.approx(196.0, abs=0.01)
    assert aria["Fptp"] == pytest.approx(30738.44, abs=0.1)


def test_labels_cover_the_quantities_we_compute():
    assert {"t", "tr", "Q0p", "Q1p", "Q2p", "Q3p", "Q4p", "Fptp"} <= set(
        GROUND_TRUTH_LABELS
    )


def test_compare_reports_both_weightings_for_quartiles():
    results = compare(CORPUS, XLSX, arias=["I"])
    quantities = {c.quantity for c in results}
    assert "Q2p (duration-weighted)" in quantities
    assert "Q2p (count-weighted)" in quantities


def test_extremes_agree_with_the_spreadsheet():
    results = {c.quantity: c for c in compare(CORPUS, XLSX, arias=["I"])}
    assert results["Q0p"].within_tolerance
    assert results["Q4p"].within_tolerance


def test_comparison_records_the_delta_even_when_out_of_tolerance():
    results = {c.quantity: c for c in compare(CORPUS, XLSX, arias=["I"])}
    entry = results["Q2p (count-weighted)"]
    assert entry.delta == pytest.approx(entry.actual - entry.expected, abs=0.01)


def test_reference_cross_check_agrees_on_extremes():
    from songfeat.validation import compare_to_reference

    results = {c.quantity: c for c in compare_to_reference(CORPUS, limit=1)}
    assert results["ref Q0p"].within_tolerance
    assert results["ref Q4p"].within_tolerance


def test_load_ground_truth_disambiguates_passaggio_blocks():
    """Fix round 1, ruling AG.

    'Hp tp'/'Mp tp'/'Lp tp' repeat once per voice-type block (LV/MV/HV
    passaggi); a flat label->value dict used to keep only the last block's
    value under each key. Values read off the sheet by hand (see
    ground-truth-layout.md) must now survive as three distinct entries.
    """
    truth = load_ground_truth(XLSX)["I"]
    assert truth["LV/Mp tp"] == pytest.approx(25.607142857142897, abs=1e-6)
    assert truth["MV/Mp tp"] == pytest.approx(21.321428571428612, abs=1e-6)
    assert truth["HV/Mp tp"] == pytest.approx(0.6785714285714286, abs=1e-6)
    assert len({truth["LV/Mp tp"], truth["MV/Mp tp"], truth["HV/Mp tp"]}) == 3


def test_compare_reports_passaggio_quantities():
    """Fix round 1, ruling AG: the shipped harness must measure passaggio
    agreement itself, not rely on an uncommitted scratch script."""
    results = {c.quantity: c for c in compare(CORPUS, XLSX, arias=["I"])}
    assert "LV/Mp tp" in results
    assert "MV/Mp tp" in results
    assert "HV/Mp tp" in results
    # Distinguishable expected values prove compare() is reading the
    # disambiguated ground truth, not three entries that collapsed to one.
    assert results["LV/Mp tp"].expected != results["HV/Mp tp"].expected


def test_total_time_pair_is_none_when_a_component_is_unmeasurable():
    """Fix round 1, ruling AH: a None component (duration unknown) must not
    be substituted with zero -- that would read as perfect agreement."""
    from songfeat.validation import _total_time

    assert _total_time(120.0, None) is None
    assert _total_time(None, 30.0) is None
    assert _total_time(120.0, 30.0) == pytest.approx(150.0)


def test_compare_reports_passaggio_percentages():
    """Fix round 2, ruling AI: a dwell time can agree with the sheet while
    its percentage disagrees, because the percentage divides by sounding
    time -- the exact quantity the overlapping-note finding implicates.
    Comparing only times is structurally blind to that, so compare() must
    emit the percentages too."""
    truth = load_ground_truth(XLSX)["I"]
    assert truth["LV/Mp %p"] == pytest.approx(15.559895833333105, abs=1e-6)

    results = {c.quantity: c for c in compare(CORPUS, XLSX, arias=["I"])}
    assert "LV/Mp %p" in results
    assert "MV/Mp %p" in results
    assert "HV/Mp %p" in results
    # Distinguishable expected values prove these are genuinely per-block,
    # not nine entries all reading the same collapsed key.
    assert results["LV/Mp %p"].expected != results["HV/Mp %p"].expected


def test_tolerance_is_chosen_by_unit_not_one_shared_default():
    """Fix round 2, ruling AJ: Hz, seconds and percentage points must each
    get their own tolerance rather than inheriting one reused constant."""
    from songfeat.validation import (
        HZ_TOLERANCE,
        PASSAGGIO_PERCENT_TOLERANCE,
        PASSAGGIO_SECONDS_TOLERANCE,
        SECONDS_TOLERANCE,
        _tolerance_for,
    )

    assert _tolerance_for("Q2p") == HZ_TOLERANCE
    assert _tolerance_for("t") == SECONDS_TOLERANCE
    assert _tolerance_for("LV/Mp tp") == PASSAGGIO_SECONDS_TOLERANCE
    assert _tolerance_for("LV/Mp %p") == PASSAGGIO_PERCENT_TOLERANCE
    # The percentage tolerance is a percentage-point judgement, not a copy
    # of the frequency tolerance that happens to share a unit-less number.
    assert PASSAGGIO_PERCENT_TOLERANCE != HZ_TOLERANCE

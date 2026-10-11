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

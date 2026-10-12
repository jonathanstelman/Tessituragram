import pytest

from songfeat.features.lyrics import advisories
from songfeat.features.lyrics.questions import Answer, Kind


def test_there_are_nine_dimensions_and_twenty_seven_columns():
    assert len(advisories.DIMENSIONS) == 9
    assert len(advisories.ADVISORY_FIELDS) == 27
    assert len(advisories.QUESTIONS) == 27


def test_intensity_is_a_six_level_score_and_the_modifiers_are_nouls():
    by_id = {question.id: question for question in advisories.QUESTIONS}
    assert by_id["advisory_violence"].kind is Kind.SCORE
    assert by_id["advisory_violence"].levels == 6, "0-5 inclusive is six levels"
    assert by_id["advisory_violence_first_person"].kind is Kind.NOUL
    assert by_id["advisory_violence_depicted"].kind is Kind.NOUL


def test_the_dimension_order_is_the_documented_tie_break_order():
    """Task 8's age_band_driver breaks ties by this order, so it is
    load-bearing rather than cosmetic."""
    assert advisories.DIMENSIONS[:5] == (
        "sex", "violence", "self_harm", "substance_use", "language",
    )


def test_columns_from_reports_the_score_and_both_modifiers():
    answers = {
        "advisory_violence": Answer("advisory_violence", score=3.4),
        "advisory_violence_first_person": Answer("advisory_violence_first_person", probability=0.81),
        "advisory_violence_depicted": Answer("advisory_violence_depicted", probability=0.12),
    }
    out = advisories.columns_from(answers)
    assert out["advisory_violence"] == 3.4
    assert out["advisory_violence_first_person"] == 0.81
    assert out["advisory_violence_depicted"] == 0.12


def test_an_unasked_advisory_is_null_and_never_zero():
    """Zero on an advisory reads as 'clean'. That is the one genuinely
    harmful output this design could produce, so it may never be a
    default."""
    out = advisories.columns_from({})
    checked = 0
    for dimension in advisories.DIMENSIONS:
        assert out[f"advisory_{dimension}"] is None, dimension
        checked += 1
    assert checked == 9


def test_an_errored_answer_is_null_and_not_a_score():
    answers = {"advisory_sex": Answer("advisory_sex", error="timeout")}
    assert advisories.columns_from(answers)["advisory_sex"] is None


def test_partial_coverage_within_a_dimension_is_reported_independently():
    """Each of a dimension's three columns is answered (or not)
    independently -- the score arriving without its modifiers, or a
    modifier arriving without the score, must not blank out its
    siblings or be papered over by them."""
    answers = {
        "advisory_sex": Answer("advisory_sex", score=1.0),
        # advisory_sex_first_person: not asked
        "advisory_sex_depicted": Answer("advisory_sex_depicted", probability=0.6),
    }
    out = advisories.columns_from(answers)
    assert out["advisory_sex"] == 1.0
    assert out["advisory_sex_first_person"] is None
    assert out["advisory_sex_depicted"] == 0.6

    # And the reverse: both modifiers present, the score absent.
    answers2 = {
        "advisory_language_first_person": Answer("advisory_language_first_person", probability=0.3),
        "advisory_language_depicted": Answer("advisory_language_depicted", probability=0.9),
    }
    out2 = advisories.columns_from(answers2)
    assert out2["advisory_language"] is None
    assert out2["advisory_language_first_person"] == 0.3
    assert out2["advisory_language_depicted"] == 0.9

import pytest

from songfeat.features.lyrics import age


def _advisories(**overrides):
    """Every advisory at zero and both modifiers low, then overridden."""
    from songfeat.features.lyrics.advisories import ADVISORY_MODIFIERS, DIMENSIONS

    columns = {}
    for dimension in DIMENSIONS:
        columns[f"advisory_{dimension}"] = 0.0
        for modifier, _text in ADVISORY_MODIFIERS:
            columns[f"advisory_{dimension}_{modifier}"] = 0.0
    columns.update(overrides)
    return columns


def test_a_clean_text_is_child():
    out = age.band_from(_advisories())
    assert out["age_band"] == "child"
    assert out["age_band_driver"] is None
    assert out["age_band_rule"] == "v1"


def test_sex_at_three_is_adult():
    out = age.band_from(_advisories(advisory_sex=3.0))
    assert out["age_band"] == "adult"
    assert out["age_band_driver"] == "sex"


def test_sex_at_one_is_adolescent():
    out = age.band_from(_advisories(advisory_sex=1.0))
    assert out["age_band"] == "adolescent"
    assert out["age_band_driver"] == "sex"


def test_depicted_violence_at_four_is_adult_but_alluded_violence_is_not():
    depicted = age.band_from(_advisories(
        advisory_violence=4.0, advisory_violence_depicted=0.9))
    alluded = age.band_from(_advisories(
        advisory_violence=4.0, advisory_violence_depicted=0.1))
    assert depicted["age_band"] == "adult"
    assert alluded["age_band"] == "adolescent", "still over the adolescent bar of 2"


def test_first_person_self_harm_at_two_is_adult_third_person_is_adolescent():
    first = age.band_from(_advisories(
        advisory_self_harm=2.0, advisory_self_harm_first_person=0.9))
    third = age.band_from(_advisories(
        advisory_self_harm=2.0, advisory_self_harm_first_person=0.1))
    assert first["age_band"] == "adult"
    assert third["age_band"] == "adolescent"


def test_first_person_death_at_three_is_adolescent_not_child():
    """The canon is full of death. Narrated death stays child-eligible;
    death the student has to voice as themselves does not."""
    out = age.band_from(_advisories(
        advisory_death=3.0, advisory_death_first_person=0.9))
    assert out["age_band"] == "adolescent"
    assert out["age_band_driver"] == "death"


def test_narrated_death_alone_does_not_raise_the_band():
    out = age.band_from(_advisories(
        advisory_death=5.0, advisory_death_first_person=0.05))
    assert out["age_band"] == "child"


def test_the_driver_is_the_highest_intensity_triggering_dimension():
    out = age.band_from(_advisories(advisory_sex=1.0, advisory_violence=4.0,
                                    advisory_violence_depicted=0.9))
    assert out["age_band"] == "adult"
    assert out["age_band_driver"] == "violence", "4.0 beats 1.0"


def test_a_tie_breaks_by_the_documented_dimension_order():
    out = age.band_from(_advisories(advisory_sex=3.0, advisory_substance_use=3.0))
    assert out["age_band_driver"] == "sex", "sex is declared before substance_use"


def test_a_null_advisory_makes_the_band_null_and_never_a_default():
    """The one genuinely harmful output this design could produce is a
    reassuring 'child' about a song nobody read. A conservative 'adult'
    is also forbidden: it would hide most of the repertoire."""
    out = age.band_from(_advisories(advisory_sex=None))
    assert out["age_band"] is None
    assert out["age_band_driver"] is None
    assert out["age_band_rule"] == "v1", "the rule version is known even when the band is not"


def test_every_advisory_null_makes_the_band_null():
    from songfeat.features.lyrics.advisories import ADVISORY_FIELDS

    out = age.band_from({field: None for field in ADVISORY_FIELDS})
    assert out["age_band"] is None


# --- Boundary tests: every threshold in rule v1 is an exact comparison,
# so each one is tested at the value and just below it. These go beyond
# the brief's sample tests because the task description calls out
# boundary coverage as a binding requirement in its own right.


@pytest.mark.parametrize(
    "field, at_threshold, just_below, threshold_band, below_band",
    [
        ("advisory_sex", 3.0, 2.9, "adult", "adolescent"),
        ("advisory_substance_use", 3.0, 2.9, "adult", "child"),
        ("advisory_language", 3.0, 2.9, "adult", "adolescent"),
        ("advisory_sex", 1.0, 0.9, "adolescent", "child"),
        ("advisory_violence", 2.0, 1.9, "adolescent", "child"),
        ("advisory_self_harm", 1.0, 0.9, "adolescent", "child"),
        ("advisory_language", 1.0, 0.9, "adolescent", "child"),
    ],
)
def test_intensity_thresholds_are_exact_not_a_floor(
    field, at_threshold, just_below, threshold_band, below_band
):
    at = age.band_from(_advisories(**{field: at_threshold}))
    below = age.band_from(_advisories(**{field: just_below}))
    assert at["age_band"] == threshold_band
    assert below["age_band"] == below_band


def test_violence_at_exactly_four_needs_depicted_strictly_above_half():
    at_half = age.band_from(_advisories(
        advisory_violence=4.0, advisory_violence_depicted=0.5))
    above_half = age.band_from(_advisories(
        advisory_violence=4.0, advisory_violence_depicted=0.51))
    assert at_half["age_band"] == "adolescent", "0.5 exactly does not fire the modifier"
    assert above_half["age_band"] == "adult"


def test_self_harm_at_exactly_two_needs_first_person_strictly_above_half():
    at_half = age.band_from(_advisories(
        advisory_self_harm=2.0, advisory_self_harm_first_person=0.5))
    above_half = age.band_from(_advisories(
        advisory_self_harm=2.0, advisory_self_harm_first_person=0.51))
    assert at_half["age_band"] == "adolescent", "0.5 exactly does not fire the modifier"
    assert above_half["age_band"] == "adult"


def test_death_at_exactly_three_needs_first_person_strictly_above_half():
    at_half = age.band_from(_advisories(
        advisory_death=3.0, advisory_death_first_person=0.5))
    above_half = age.band_from(_advisories(
        advisory_death=3.0, advisory_death_first_person=0.51))
    assert at_half["age_band"] == "child", "0.5 exactly does not fire the modifier"
    assert above_half["age_band"] == "adolescent"


def test_violence_below_adult_threshold_but_above_adolescent_is_adolescent():
    below_adult = age.band_from(_advisories(
        advisory_violence=3.9, advisory_violence_depicted=1.0))
    assert below_adult["age_band"] == "adolescent", "violence below 4 can't be adult regardless of depicted"


# --- Fix round 1: the precondition is exactly the nine columns rule v1
# reads, not all 27 advisory columns. The spec commits to "one failed
# batch nulls its own columns and no others," so a batch holding only
# positive_messages/role_models/religious_content (or a modifier no
# clause reads) must never null age_band on its own.


def test_only_the_nine_rule_inputs_need_be_present():
    """This is the test that would have failed under the old,
    over-broad precondition: every OTHER advisory column is simply
    absent from the dict (as it would be if its batch had failed, or
    had not been asked), and the band is still a real verdict."""
    columns = {field: 0.0 for field in age._RULE_INPUTS}
    out = age.band_from(columns)
    assert out["age_band"] == "child"
    assert out["age_band_driver"] is None
    assert out["age_band_rule"] == "v1"


def test_each_of_the_nine_rule_inputs_missing_nulls_the_band():
    checked = 0
    for missing_field in age._RULE_INPUTS:
        columns = {field: 0.0 for field in age._RULE_INPUTS}
        columns[missing_field] = None
        out = age.band_from(columns)
        assert out["age_band"] is None, missing_field
        assert out["age_band_driver"] is None, missing_field
        assert out["age_band_rule"] == "v1", missing_field
        checked += 1
    assert checked == 9


def test_the_nine_rule_inputs_are_exactly_these_and_no_others():
    """Pins the input set itself, not just its size, so a future edit
    to rule v1 that silently widens or narrows what it reads is
    caught here rather than only in a derived test's behaviour."""
    assert set(age._RULE_INPUTS) == {
        "advisory_sex",
        "advisory_violence", "advisory_violence_depicted",
        "advisory_self_harm", "advisory_self_harm_first_person",
        "advisory_substance_use",
        "advisory_language",
        "advisory_death", "advisory_death_first_person",
    }

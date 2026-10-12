import pytest

from songfeat.features.lyrics import perspective
from songfeat.features.lyrics.questions import Answer, Kind


def _answers(**overrides):
    """Every perspective question answered, so a test changes one thing."""
    base = {
        "narrator_gender": Answer("narrator_gender", choice="unspecified"),
        "relational_focus_present": Answer("relational_focus_present", probability=0.05),
        "relationship_is_romantic": Answer("relationship_is_romantic", probability=0.02),
        "addressee_present": Answer("addressee_present", probability=0.05),
        "love_interest_gender": Answer("love_interest_gender", choice="unspecified"),
    }
    for subject in ("narrator", "love_interest"):
        for mechanism in ("pronouns", "address", "agreement", "named_role", "biology"):
            key = f"{subject}_cast_by_{mechanism}"
            base[key] = Answer(key, probability=0.02)
    base.update({key: Answer(key, **value) for key, value in overrides.items()})
    return base


def test_there_are_fifteen_questions_and_nineteen_columns():
    assert len(perspective.QUESTIONS) == 15
    assert len(perspective.PERSPECTIVE_FIELDS) == 19


def test_gender_is_a_choice_including_unspecified():
    by_id = {question.id: question for question in perspective.QUESTIONS}
    assert by_id["narrator_gender"].kind is Kind.CHOICE
    assert "unspecified" in by_id["narrator_gender"].options
    assert by_id["narrator_gender"].options == (
        "female", "male", "non_binary", "collective", "unspecified",
    )


def test_pronouns_alone_cost_one():
    out = perspective.columns_from(_answers(
        narrator_cast_by_pronouns={"probability": 0.97},
    ))
    assert out["narrator_gender_cast"] == 1
    assert out["gender_adaptation_cost"] == 1
    assert out["gender_adaptation_blocker"] == "pronouns"


def test_a_named_role_costs_five_and_is_the_blocker():
    out = perspective.columns_from(_answers(
        narrator_cast_by_named_role={"probability": 0.91},
    ))
    assert out["narrator_gender_cast"] == 5
    assert out["gender_adaptation_blocker"] == "named_role"


def test_the_costlier_mechanism_wins_when_two_fire():
    """Corpus song cast-two-mechanisms: pronouns AND a named role."""
    out = perspective.columns_from(_answers(
        narrator_cast_by_pronouns={"probability": 0.95},
        narrator_cast_by_named_role={"probability": 0.88},
    ))
    assert out["gender_adaptation_cost"] == 5
    assert out["gender_adaptation_blocker"] == "named_role"


def test_a_tie_at_equal_cost_breaks_by_declaration_order():
    """named_role and biology both cost 5; named_role is declared first."""
    out = perspective.columns_from(_answers(
        narrator_cast_by_named_role={"probability": 0.80},
        narrator_cast_by_biology={"probability": 0.90},
    ))
    assert out["gender_adaptation_cost"] == 5
    assert out["gender_adaptation_blocker"] == "named_role"


def test_no_mechanism_firing_is_a_real_zero_with_no_blocker():
    out = perspective.columns_from(_answers())
    assert out["narrator_gender_cast"] == 0
    assert out["gender_adaptation_cost"] == 0
    assert out["gender_adaptation_blocker"] is None


def test_the_love_interest_columns_are_null_when_there_is_no_relational_focus():
    """The Tom's Diner case. Gendered people are present; none of them is
    the song's relational focus, so there is nothing to be undefined
    ABOUT -- and null is the only honest answer. Not 0.0, which would
    read as 'the beloved's gender is not cast'."""
    out = perspective.columns_from(_answers(
        relational_focus_present={"probability": 0.04},
        love_interest_gender={"choice": "female"},
        love_interest_cast_by_pronouns={"probability": 0.99},
    ))
    assert out["love_interest_gender"] is None
    assert out["love_interest_gender_cast"] is None
    assert out["love_interest_cast_by_pronouns"] is None


def test_the_love_interest_columns_populate_when_the_focus_is_present():
    out = perspective.columns_from(_answers(
        relational_focus_present={"probability": 0.95},
        relationship_is_romantic={"probability": 0.89},
        love_interest_gender={"choice": "male"},
        love_interest_cast_by_pronouns={"probability": 0.94},
    ))
    assert out["love_interest_gender"] == "male"
    assert out["love_interest_gender_cast"] == 1


def test_narrator_casting_is_never_gated_on_relational_focus():
    """A song written unmistakably from a man's perspective is worth
    flagging whether or not anyone is being sung to."""
    out = perspective.columns_from(_answers(
        relational_focus_present={"probability": 0.01},
        narrator_gender={"choice": "male"},
        narrator_cast_by_biology={"probability": 0.93},
    ))
    assert out["narrator_gender"] == "male"
    assert out["narrator_gender_cast"] == 5


def test_adaptation_cost_takes_the_worse_of_the_two_subjects():
    out = perspective.columns_from(_answers(
        relational_focus_present={"probability": 0.95},
        narrator_cast_by_pronouns={"probability": 0.95},
        love_interest_cast_by_address={"probability": 0.92},
    ))
    assert out["narrator_gender_cast"] == 1
    assert out["love_interest_gender_cast"] == 3
    assert out["gender_adaptation_cost"] == 3
    assert out["gender_adaptation_blocker"] == "address"


def test_unspecified_is_a_real_answer_and_not_null():
    out = perspective.columns_from(_answers())
    assert out["narrator_gender"] == "unspecified"


def test_everything_is_null_when_nothing_was_asked():
    out = perspective.columns_from({})
    for field in perspective.PERSPECTIVE_FIELDS:
        assert out[field] is None, field


def test_an_unrecognised_choice_value_becomes_null_not_unspecified():
    """A Choice answer arriving outside the declared option set must
    become None with a reason -- never be coerced to "unspecified",
    which would turn "we got something we don't understand" into a
    real answer."""
    out = perspective.columns_from(_answers(
        narrator_gender={"choice": "trans-masc"},
    ))
    assert out["narrator_gender"] is None


def test_partial_coverage_absent_columns_are_null_and_cost_uses_what_is_present():
    """A core-set run asks narrator_gender, narrator_cast_by_pronouns,
    relational_focus_present and love_interest_gender -- but none of the
    other cast mechanisms. The absent mechanism columns must read None,
    not 0.0, and the derived cost must be computed only from what was
    actually asked."""
    answers = {
        "narrator_gender": Answer("narrator_gender", choice="male"),
        "narrator_cast_by_pronouns": Answer("narrator_cast_by_pronouns", probability=0.9),
        "relational_focus_present": Answer("relational_focus_present", probability=0.9),
        "love_interest_gender": Answer("love_interest_gender", choice="female"),
    }
    out = perspective.columns_from(answers)

    # The one narrator mechanism that was asked is populated; the four
    # that were never asked stay null rather than reading as "0.0 (not
    # established)".
    assert out["narrator_cast_by_pronouns"] == 0.9
    unasked = ("address", "agreement", "named_role", "biology")
    none_count = sum(
        1 for mechanism in unasked if out[f"narrator_cast_by_{mechanism}"] is None
    )
    assert none_count == len(unasked)

    # The cost is computed from the one mechanism present, not from an
    # absence treated as "nothing fired here either".
    assert out["narrator_gender_cast"] == 1
    assert out["gender_adaptation_blocker"] == "pronouns"

    # love_interest's gate is open but none of its own mechanisms were
    # asked, so love_interest_gender_cast is a real zero (seen, nothing
    # fired) rather than null.
    assert out["love_interest_gender"] == "female"
    assert out["love_interest_gender_cast"] is None
    li_unasked = ("pronouns", "address", "agreement", "named_role", "biology")
    li_none_count = sum(
        1 for mechanism in li_unasked if out[f"love_interest_cast_by_{mechanism}"] is None
    )
    assert li_none_count == len(li_unasked)

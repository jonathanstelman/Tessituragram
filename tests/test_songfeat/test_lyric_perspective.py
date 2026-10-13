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


def test_the_derived_cost_columns_are_int_not_float():
    """CAST_MECHANISMS holds five integer costs; the derived columns are
    a lookup into that table, never a model-returned probability-weighted
    mean, so they can only land on 0, 1, 3, 4 or 5. ``== 1`` alone would
    also pass for ``1.0``, which is exactly the regression this guards:
    a float here would serialise as "1.0" in a human-facing CSV/JSON
    column whose values are meant to read as a discrete cost."""
    out = perspective.columns_from(_answers(
        narrator_cast_by_pronouns={"probability": 0.97},
    ))
    assert isinstance(out["narrator_gender_cast"], int)
    assert not isinstance(out["narrator_gender_cast"], bool)
    assert isinstance(out["gender_adaptation_cost"], int)
    assert not isinstance(out["gender_adaptation_cost"], bool)

    score, _blocker = perspective.cast_score(_answers(
        narrator_cast_by_pronouns={"probability": 0.97},
    ), "narrator")
    assert isinstance(score, int)
    assert not isinstance(score, bool)


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
    assert isinstance(out["narrator_gender_cast"], int)
    assert out["gender_adaptation_cost"] == 0
    assert isinstance(out["gender_adaptation_cost"], int)
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


def test_partial_coverage_nulls_the_cast_score_rather_than_under_reporting_it():
    """A core-set run asks narrator_gender, narrator_cast_by_pronouns,
    relational_focus_present and love_interest_gender -- but none of the
    other cast mechanisms. The absent mechanism columns must read None,
    not 0.0, and so must the cast score and the derived cost.

    This test was inverted before the fix wave: it pinned
    ``narrator_gender_cast == 1`` and ``blocker == "pronouns"`` from
    the one mechanism that happened to be answered. Because the cost is
    a MAX, that can only under-report -- "swap the pronouns and you're
    done" for a text whose ``named_role``/``biology`` answers were
    never read and might have made it cost 5, not adaptable at all.
    A lean run showed exactly that in real output: cost 0, blocker
    null, which reads as "nothing to change"."""
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

    # Four of the five mechanisms were never read, so there is no
    # trustworthy cost: null, in the one direction that matters.
    assert out["narrator_gender_cast"] is None
    assert out["gender_adaptation_cost"] is None
    assert out["gender_adaptation_blocker"] is None

    # love_interest's gate is open but none of its own mechanisms were
    # asked either, so its cast score is null too.
    assert out["love_interest_gender"] == "female"
    assert out["love_interest_gender_cast"] is None
    li_unasked = ("pronouns", "address", "agreement", "named_role", "biology")
    li_none_count = sum(
        1 for mechanism in li_unasked if out[f"love_interest_cast_by_{mechanism}"] is None
    )
    assert li_none_count == len(li_unasked)


def test_one_missing_mechanism_nulls_that_subject_and_the_derived_cost():
    """``age.band_from``'s all-or-nothing precondition, applied here for
    a stronger reason: the cost is a MAX, so a missing mechanism can only
    make it read too low. With named_role and biology missing, a text
    that is not adaptable at all read cost 1, blocker "pronouns" --
    "swap freely" -- with nothing in the row saying anything was
    missed."""
    answers = _answers(narrator_cast_by_pronouns={"probability": 0.97})
    del answers["narrator_cast_by_named_role"]

    out = perspective.columns_from(answers)
    assert out["narrator_gender_cast"] is None
    assert out["gender_adaptation_cost"] is None
    assert out["gender_adaptation_blocker"] is None
    # The four mechanisms that WERE answered still report their own
    # probabilities: it is the derived number that is withheld.
    assert out["narrator_cast_by_pronouns"] == 0.97
    answered = sum(
        1 for mechanism in ("pronouns", "address", "agreement", "biology")
        if out[f"narrator_cast_by_{mechanism}"] is not None
    )
    assert answered == 4


def test_an_errored_mechanism_answer_nulls_the_cost_too():
    """An answer that came back as an error is not an answer. Same
    precondition, different cause."""
    answers = _answers(narrator_cast_by_pronouns={"probability": 0.97})
    answers["narrator_cast_by_biology"] = Answer(
        "narrator_cast_by_biology", error="HTTP 503")

    out = perspective.columns_from(answers)
    assert out["narrator_cast_by_biology"] is None
    assert out["narrator_gender_cast"] is None
    assert out["gender_adaptation_cost"] is None


def test_an_equal_cost_tie_between_the_subjects_names_the_narrator():
    """Both subjects cast by the same mechanism at the same cost. The
    blocker resolves by SUBJECTS order -- narrator first -- which is
    deterministic, load-bearing for the first driving use case, and was
    untested. The narrator wins because its casting is the one that
    always applies: it is never gated."""
    out = perspective.columns_from(_answers(
        relational_focus_present={"probability": 0.99},
        narrator_cast_by_agreement={"probability": 0.9},
        love_interest_cast_by_agreement={"probability": 0.9},
    ))
    assert out["narrator_gender_cast"] == 4
    assert out["love_interest_gender_cast"] == 4
    assert out["gender_adaptation_cost"] == 4
    assert out["gender_adaptation_blocker"] == "agreement"
    assert perspective.SUBJECTS[0][0] == "narrator", (
        "the tie-break is SUBJECTS order; pin the order the tie-break "
        "depends on rather than leaving it incidental"
    )


def test_the_worse_subject_sets_the_cost_and_names_its_own_mechanism():
    """Not a tie: the love interest is cast by a biological detail (5,
    not adaptable) while the narrator is cast only by pronouns (1). The
    teacher must be told the expensive one."""
    out = perspective.columns_from(_answers(
        relational_focus_present={"probability": 0.99},
        narrator_cast_by_pronouns={"probability": 0.9},
        love_interest_cast_by_biology={"probability": 0.9},
    ))
    assert out["narrator_gender_cast"] == 1
    assert out["love_interest_gender_cast"] == 5
    assert out["gender_adaptation_cost"] == 5
    assert out["gender_adaptation_blocker"] == "biology"

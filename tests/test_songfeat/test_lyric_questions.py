import pytest

from songfeat.features.lyrics import questions as q


def test_every_question_id_is_unique():
    ids = [question.id for question in q.question_set("full")]
    assert len(ids) == len(set(ids)), "duplicate question id"


def test_every_question_populates_exactly_one_column_and_no_column_twice():
    columns = [question.column for question in q.question_set("full")]
    assert len(columns) == len(set(columns))


def test_no_question_text_contains_a_format_placeholder():
    """Question text is a fixed constant: nothing from a lyric may ever
    be interpolated into it. A stray {} is how that rule gets broken."""
    offenders = [x.id for x in q.question_set("full")
                 if "{" in x.text or "%s" in x.text]
    assert offenders == []


def test_every_question_declares_what_its_kind_needs():
    violations = []
    for question in q.question_set("full"):
        if question.kind is q.Kind.CHOICE:
            if len(question.options) < 2 or "unspecified" not in question.options:
                violations.append(question.id)
        elif question.kind is q.Kind.SCORE:
            if not (2 <= question.levels <= 10):
                violations.append(question.id)
        elif question.kind is q.Kind.NOUL:
            if question.options or question.levels:
                violations.append(question.id)
    assert violations == []


@pytest.mark.xfail(reason="axes land in Tasks 5-8", strict=True)
def test_the_core_set_is_a_subset_of_the_full_set():
    full_ids = {question.id for question in q.question_set("full")}
    assert q.CORE_IDS <= full_ids


@pytest.mark.xfail(reason="axes land in Tasks 5-8", strict=True)
def test_the_core_set_is_thirteen_questions_and_fits_one_call():
    core = q.question_set("core")
    assert len(core) == 13
    assert len(core) <= q.BATCH_LIMIT


@pytest.mark.xfail(reason="axes land in Tasks 5-8", strict=True)
def test_the_core_set_covers_every_question_kind_and_every_axis_it_claims():
    core = q.question_set("core")
    assert {question.kind for question in core} == set(q.Kind)
    assert {question.axis for question in core} == {
        "themes", "tone", "advisories", "perspective", "sensitive", "meta",
    }


def test_an_unknown_set_name_raises_rather_than_falling_back():
    with pytest.raises(ValueError, match="unknown question set"):
        q.question_set("cheap")

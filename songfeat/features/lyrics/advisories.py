"""Content advisories: intensity, plus who voices it and how directly.

A flat intensity score is useless on this repertoire. Rated plainly,
violence flags Erlkoenig, Butterfly, Carmen and most of the Romantic
lied, so any filter strict enough to exclude a contemporary explicit
lyric also excludes half the teaching canon. The fix is not to discount
period drama -- a thirteen-year-old singing Butterfly's suicide aria is
a real pedagogical decision, not a false positive.

What distinguishes it is peculiar to PERFORMED repertoire: whether the
student has to inhabit it in the first person. "I will die by my own
hand" is a different thing to ask of a student than "she died". With the
two modifiers a teacher can ask the question they actually have --
nothing my student has to sing as themselves -- rather than "nothing
violent".
"""

from __future__ import annotations

from typing import Any

from ...model import Part, Piece
from ..base import feature
from .questions import Answer, Kind, Question, register
from .service import classify_part, error_summary
from .vocabulary import ADVISORIES, ADVISORY_MODIFIERS

#: Dimension slugs in age-band tie-break order (Task 8 depends on this).
DIMENSIONS: tuple[str, ...] = tuple(slug for slug, _text in ADVISORIES)

#: 0-5 inclusive is six ordered levels.
LEVELS = 6


def _build() -> tuple[tuple[Question, ...], tuple[str, ...]]:
    questions: list[Question] = []
    fields: list[str] = []
    for slug, text in ADVISORIES:
        column = f"advisory_{slug}"
        questions.append(Question(
            id=column, kind=Kind.SCORE, text=text,
            column=column, axis="advisories", levels=LEVELS,
        ))
        fields.append(column)
        for modifier, modifier_text in ADVISORY_MODIFIERS:
            modifier_column = f"{column}_{modifier}"
            questions.append(Question(
                id=modifier_column, kind=Kind.NOUL,
                text=f"{text.rstrip('?')}? {modifier_text}",
                column=modifier_column, axis="advisories",
            ))
            fields.append(modifier_column)
    return tuple(questions), tuple(fields)


QUESTIONS, ADVISORY_FIELDS = _build()
register(QUESTIONS)


def columns_from(answers: dict[str, Answer]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for slug in DIMENSIONS:
        column = f"advisory_{slug}"
        answer = answers.get(column)
        out[column] = answer.score if answer and not answer.error else None
        for modifier, _text in ADVISORY_MODIFIERS:
            modifier_column = f"{column}_{modifier}"
            modifier_answer = answers.get(modifier_column)
            out[modifier_column] = (
                modifier_answer.probability
                if modifier_answer and not modifier_answer.error
                else None
            )
    return out


@feature(
    name="lyrics_advisories", group="lyrics", scope="part", source="songfeat",
    description=(
        "Nine content dimensions, each a 0-5 intensity plus two modifiers: "
        "whether the singer voices it in the first person, and whether the "
        "text depicts it rather than alluding to it. Anchored on Common "
        "Sense Media's content grid, minus consumerism, plus death, "
        "self-harm and religious content -- the last a filter need rather "
        "than a warning. NEVER DEFAULTS: a zero here reads as 'clean', so "
        "an unread song reports null, not zero."
    ),
    fields=ADVISORY_FIELDS,
    best_with=("musicxml",),
    # The one opt-in group: it is neither offline nor free, so an
    # unfiltered run leaves it out entirely (see FeatureSpec.opt_in).
    opt_in=True,
)
def lyrics_advisories(part: Part, piece: Piece) -> dict[str, Any]:
    classification = classify_part(part, piece)
    if classification.reason is not None:
        return {name: None for name in ADVISORY_FIELDS}
    out = columns_from(classification.answers)
    # A question that came back as an error nulls its own column; its
    # reason goes to the record's error channel rather than being
    # dropped, which would leave a null nothing in the row explains.
    failures = error_summary(classification.answers, ADVISORY_FIELDS)
    if failures is not None:
        out["_errors"] = {"lyrics_advisories": failures}
    return out

"""The tone axis: how a text treats its subject."""

from __future__ import annotations

from typing import Any

from ...model import Part, Piece
from ..base import feature
from .questions import Answer, Kind, Question, register
from .service import classify_part, error_summary
from .vocabulary import TONES

QUESTIONS: tuple[Question, ...] = tuple(
    Question(id=f"tone_{slug}", kind=Kind.NOUL, text=text,
             column=f"tone_{slug}", axis="tone")
    for slug, text in TONES
)
TONE_FIELDS: tuple[str, ...] = tuple(question.column for question in QUESTIONS)
register(QUESTIONS)


def columns_from(answers: dict[str, Answer]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for column in TONE_FIELDS:
        answer = answers.get(column)
        out[column] = answer.probability if answer and not answer.error else None
    return out


@feature(
    name="lyrics_tone", group="lyrics", scope="part", source="songfeat",
    description=(
        "How the text treats its subject rather than what it is about: "
        "comic, ironic, sincere, elegiac, playful, grand. Not mutually "
        "exclusive -- a wry song about unrequited love is comic and ironic "
        "and barely sincere. Each is a probability; null when the "
        "classifier did not run."
    ),
    fields=TONE_FIELDS,
    best_with=("musicxml",),
    # The one opt-in group: it is neither offline nor free, so an
    # unfiltered run leaves it out entirely (see FeatureSpec.opt_in).
    opt_in=True,
)
def lyrics_tone(part: Part, piece: Piece) -> dict[str, Any]:
    classification = classify_part(part, piece)
    if classification.reason is not None:
        return {name: None for name in TONE_FIELDS}
    out = columns_from(classification.answers)
    # A question that came back as an error nulls its own column; its
    # reason goes to the record's error channel rather than being
    # dropped, which would leave a null nothing in the row explains.
    failures = error_summary(classification.answers, TONE_FIELDS)
    if failures is not None:
        out["_errors"] = {"lyrics_tone": failures}
    return out

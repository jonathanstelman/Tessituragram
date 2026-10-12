"""The themes axis: two tiers, multi-label, with a divergence flag.

Both tiers are asked independently rather than deriving the family from
its children. A song can be about love in a way no child theme catches,
and a child can fire while the family reads low. Either case is worth
seeing while the vocabulary is young, so the divergence flag surfaces it
instead of reconciling it. A divergence is not an error.
"""

from __future__ import annotations

from typing import Any

from ...model import Part, Piece
from ..base import feature
from .questions import Answer, Kind, Question, register
from .service import classify_part
from .vocabulary import THEMES

#: A probability at or above this is "fires". Used only for the
#: divergence flag; every probability is reported unrounded.
FIRES = 0.5


def _build() -> tuple[tuple[Question, ...], tuple[str, ...]]:
    questions: list[Question] = []
    fields: list[str] = []
    for family, (family_text, children) in THEMES.items():
        column = f"theme_{family}"
        questions.append(Question(
            id=column, kind=Kind.NOUL, text=family_text,
            column=column, axis="themes",
        ))
        fields.append(column)
        for slug, text in children:
            child_column = f"theme_{family}_{slug}"
            questions.append(Question(
                id=child_column, kind=Kind.NOUL, text=text,
                column=child_column, axis="themes",
            ))
            fields.append(child_column)
        fields.append(f"theme_{family}_divergence")
    return tuple(questions), tuple(fields)


QUESTIONS, THEME_FIELDS = _build()
register(QUESTIONS)


def columns_from(answers: dict[str, Answer]) -> dict[str, Any]:
    """Map answers to columns. Pure; unasked questions stay None."""
    out: dict[str, Any] = {}
    for family, (_text, children) in THEMES.items():
        family_column = f"theme_{family}"
        family_answer = answers.get(family_column)
        out[family_column] = family_answer.probability if family_answer else None

        child_values: list[float | None] = []
        for slug, _child_text in children:
            column = f"theme_{family}_{slug}"
            answer = answers.get(column)
            value = answer.probability if answer else None
            out[column] = value
            child_values.append(value)

        known = [value for value in child_values if value is not None]
        if out[family_column] is None or not known:
            out[f"theme_{family}_divergence"] = None
        else:
            family_fires = out[family_column] >= FIRES
            any_child_fires = max(known) >= FIRES
            out[f"theme_{family}_divergence"] = (
                1.0 if family_fires != any_child_fires else 0.0
            )
    return out


@feature(
    name="lyrics_themes", group="lyrics", scope="part", source="songfeat",
    description=(
        "What the text is about, over a two-tier vocabulary anchored on the "
        "Poetry Foundation's subject taxonomy: 9 families and 56 children, "
        "multi-label, each a probability. Both tiers are asked "
        "independently; a family column is what was asked, not the maximum "
        "of its children. ``theme_<family>_divergence`` is 1.0 when the "
        "family and its children disagree about whether the theme is "
        "present, which means either the subject falls between the leaves "
        "or a leaf fired spuriously -- a signal to read the song, not an "
        "error. Null when the classifier did not run."
    ),
    fields=THEME_FIELDS,
    best_with=("musicxml",),
)
def lyrics_themes(part: Part, piece: Piece) -> dict[str, Any]:
    classification = classify_part(part, piece)
    if classification.reason is not None:
        return {name: None for name in THEME_FIELDS}
    return columns_from(classification.answers)

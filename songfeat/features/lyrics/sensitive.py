"""Subjects a particular student may need to avoid entirely.

Unlike the advisories, this axis answers no general question and
produces no verdict. Its job is to find the songs to rule out for one
person -- a student who has recently lost a parent cannot sing an elegy
for one, however well it fits otherwise.

Three properties follow from that, and all three are load-bearing:

1. It NEVER aggregates. Sensitivity is a relation between a song and one
   student; a composite would be pretending to know the student.
2. Centrality matters more than intensity, so each subject carries a
   centrality score -- a passing line about a dead father is not an
   elegy for one.
3. First person matters: "my mother is gone" is not "her mother was
   gone".

NOTHING ABOUT A STUDENT IS EVER STORED. The songs carry flags; the
knowledge that one student is bereaved stays with the teacher, and the
matching is ephemeral. That is a privacy boundary, and it is also why
point 1 holds.
"""

from __future__ import annotations

from typing import Any

from ...model import Part, Piece
from ..base import feature
from .questions import Answer, Kind, Question, register
from .service import classify_part
from .vocabulary import SENSITIVE

SUBJECTS: tuple[str, ...] = tuple(slug for slug, _text in SENSITIVE)
LEVELS = 6


def _build() -> tuple[tuple[Question, ...], tuple[str, ...]]:
    questions: list[Question] = []
    fields: list[str] = []
    for slug, text in SENSITIVE:
        column = f"sensitive_{slug}"
        questions.append(Question(
            id=column, kind=Kind.NOUL, text=text,
            column=column, axis="sensitive",
        ))
        questions.append(Question(
            id=f"{column}_centrality", kind=Kind.SCORE, levels=LEVELS,
            text=f"{text.rstrip('?')}? How central is it to the text as a whole?",
            column=f"{column}_centrality", axis="sensitive",
        ))
        questions.append(Question(
            id=f"{column}_first_person", kind=Kind.NOUL,
            text=f"{text.rstrip('?')}? Is it the singer's own, rather than someone else's?",
            column=f"{column}_first_person", axis="sensitive",
        ))
        fields.extend([column, f"{column}_centrality", f"{column}_first_person"])
    return tuple(questions), tuple(fields)


QUESTIONS, SENSITIVE_FIELDS = _build()
register(QUESTIONS)


def columns_from(answers: dict[str, Answer]) -> dict[str, Any]:
    """Map answers to columns. Pure; unasked questions stay None.

    No column here is ever a function of another column: each of the
    39 is read straight off its own answer, which is what keeps this
    axis free of the composite the module docstring forbids.
    """
    out: dict[str, Any] = {}
    for slug in SUBJECTS:
        column = f"sensitive_{slug}"
        presence = answers.get(column)
        out[column] = presence.probability if presence and not presence.error else None
        centrality = answers.get(f"{column}_centrality")
        out[f"{column}_centrality"] = (
            centrality.score if centrality and not centrality.error else None
        )
        first_person = answers.get(f"{column}_first_person")
        out[f"{column}_first_person"] = (
            first_person.probability if first_person and not first_person.error else None
        )
    return out


@feature(
    name="lyrics_sensitive", group="lyrics", scope="part", source="songfeat",
    description=(
        "Thirteen subjects a particular student may need to avoid "
        "entirely, each with a presence probability, how central it is to "
        "the text (0-5), and whether it is the singer's own rather than "
        "someone else's. THERE IS DELIBERATELY NO COMPOSITE: sensitivity "
        "is a relation between a song and one student, and no number here "
        "could know anything about the student. The list is not exhaustive "
        "and never will be -- it grows by release -- so an absent flag "
        "means 'not among these thirteen', not 'nothing sensitive here'. "
        "Note that ``sensitive_suicide`` and ``sensitive_self_harm`` "
        "deliberately overlap ``advisory_self_harm``: the advisory is a "
        "graded intensity feeding the age band, these are presence and "
        "centrality feeding a per-student exclusion. Different questions."
    ),
    fields=SENSITIVE_FIELDS,
    best_with=("musicxml",),
)
def lyrics_sensitive(part: Part, piece: Piece) -> dict[str, Any]:
    classification = classify_part(part, piece)
    if classification.reason is not None:
        return {name: None for name in SENSITIVE_FIELDS}
    return columns_from(classification.answers)

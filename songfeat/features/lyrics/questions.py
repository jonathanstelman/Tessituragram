"""The typed questions put to the classifier.

Every question's text is a constant here. Nothing from a lyric is ever
interpolated into it: the model does not treat its state as hostile, so
a lyric that reads like an instruction must stay data. Keeping the
question text fixed means the worst case is a wrong classification
inside a bounded, typed output set.

The sets are versioned (``core@v1``, ``full@v1``) and recorded in the
output, so a leanly-built database cannot be mistaken for a complete
one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

#: The provider endpoint's questions-per-call cap.
BATCH_LIMIT = 20


class Kind(StrEnum):
    NOUL = "noul"      # yes/no, returns a probability
    CHOICE = "choice"  # one of a fixed option set
    SCORE = "score"    # 2-10 ordered levels, probability-weighted mean


@dataclass(frozen=True)
class Question:
    id: str
    kind: Kind
    text: str
    column: str
    axis: str
    options: tuple[str, ...] = ()
    levels: int = 0


@dataclass(frozen=True)
class Answer:
    """One question's result, or why there isn't one."""

    question_id: str
    probability: float | None = None
    choice: str | None = None
    score: float | None = None
    confidence: float | None = None
    error: str | None = None


SET_VERSIONS = {"core": "core@v1", "full": "full@v1"}


#: Axis modules register themselves at import. This is not a style
#: choice: an eager ``from . import themes, tone, ...`` here would make
#: this module unimportable until every axis exists, so nothing could be
#: built or tested incrementally. It also keeps the dependency pointing
#: one way -- axes know about questions, questions knows nothing about
#: axes.
_REGISTERED: list[Question] = []


def register(questions: tuple[Question, ...]) -> None:
    """Called once per axis module, at import time."""
    _REGISTERED.extend(questions)


#: The 13 questions of the lean set, chosen to exercise every code path
#: rather than to sample the vocabulary: both theme tiers and their
#: divergence flag, a Score with both modifiers (which are also the
#: age-band inputs), a Choice, the relational-focus gate with one gated
#: column, a flag that must never aggregate, and the language Choice.
CORE_IDS = frozenset({
    "theme_love",
    "theme_love_unrequited",
    "tone_comic",
    "advisory_violence",
    "advisory_violence_first_person",
    "advisory_violence_depicted",
    "narrator_gender",
    "narrator_cast_by_pronouns",
    "relational_focus_present",
    "love_interest_gender",
    "sensitive_loss_of_parent",
    "sensitive_loss_of_parent_centrality",
    "lyrics_language",
})


def question_set(name: str) -> tuple[Question, ...]:
    """The live question set. Reads ``_REGISTERED``, so it reflects
    whichever axes have been imported -- which is what lets the axes
    land one task at a time."""
    if name == "full":
        return tuple(_REGISTERED)
    if name == "core":
        return tuple(q for q in _REGISTERED if q.id in CORE_IDS)
    raise ValueError(f"unknown question set: {name!r}")

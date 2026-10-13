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

import json
from dataclasses import dataclass
from enum import StrEnum

#: The questions-per-call cap. **Measured, not assumed**, as of
#: 2026-10-12: the docs at https://docs.typesafe.ai never state a
#: maximum, so this was confirmed by sending exactly 20 trivial Noul
#: questions in a single live call to
#: ``https://api.typesafe.ai/v1/systemone`` and observing all 20 answer
#: cleanly in that one call (see
#: ``tests/test_songfeat/test_lyric_client.py::test_the_real_api_accepts_a_full_batch_of_twenty``).
#: That confirms the cap is *at least* 20 -- it does not rule out a
#: higher real cap, which would just mean fewer, cheaper calls if ever
#: raised. It is this value, 20, that matters: the client batches to it,
#: so a cap lower than 20 is the one failure mode that would silently
#: break every full run, and that is what was checked.
BATCH_LIMIT = 20

#: The shared v1 criteria rubric for every Score question (0-5 levels).
#:
#: It exists so the scale means the same thing on every song and every
#: call. The derived age band tests Score outputs against absolute
#: thresholds (``advisory_sex >= 3``, ``advisory_violence >= 4``,
#: ``advisory_self_harm >= 2``, ``advisory_language >= 1``), and those
#: thresholds only mean something if "3" is the same severity on every
#: run rather than a scale the model invents per call. Sent to the
#: classifier as a question's ``criteria`` when the question does not
#: carry its own (see ``Question.criteria`` below), by every Score
#: dimension: violence, sex, death, language, and the sensitive-subject
#: centrality scores, so the wording is deliberately dimension-neutral
#: rather than naming any one of them.
#:
#: This is the v1 approach: one shared rubric rather than per-question
#: rubric text for all 153 questions, which is real design work and not
#: this task's to invent. ``Question.criteria`` is the seam for that --
#: a later task can give an individual question its own rubric (its own
#: tuple of level descriptions, or a mapping for Noul/Choice) without
#: reshaping anything here.
SCORE_LEVELS: tuple[str, ...] = (
    "absent -- the subject does not appear at all",
    "passing -- a brief or oblique reference only, easy to miss",
    "present -- clearly there, but not a focus of the lyric",
    "central -- a significant focus, described with some detail",
    "strong -- explicit, sustained, or graphic",
    "pervasive -- explicit and dominant throughout the lyric",
)


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
    #: An individual rubric for this question, overriding the shared
    #: default the client otherwise sends (``SCORE_LEVELS`` for Score,
    #: generic yes/no or option-name criteria for Noul/Choice). Unset
    #: for every question declared so far -- this is the seam for a
    #: later task to add per-question rubric text, not something this
    #: plan's 153 questions use yet.
    criteria: tuple[str, ...] | dict[str, str] | None = None


@dataclass(frozen=True)
class Answer:
    """One question's result, or why there isn't one."""

    question_id: str
    probability: float | None = None
    choice: str | None = None
    score: float | None = None
    confidence: float | None = None
    error: str | None = None


def resolved_criteria(question: Question) -> dict[str, str] | list[str]:
    """The disambiguating description(s) the live API requires alongside
    ``instructions`` -- a 400 ("Noul question must have criteria or
    instructions") is what happens without one.

    A question's own ``criteria`` wins when it is set (the seam for a
    later task's per-question rubrics). Otherwise: Noul and Choice fall
    back to generic criteria, which is harmless because the question
    text already carries the judgment and the option names are
    self-describing. Score falls back to ``SCORE_LEVELS``, the shared
    dimension-neutral 0-5 rubric -- *not* a generic placeholder,
    because the derived age band tests Score outputs against absolute
    thresholds (e.g. ``advisory_sex >= 3``), which only mean something
    if "3" is the same severity on every call rather than a scale the
    model invents each time.

    This is the single resolution path both the client (what gets sent)
    and the cache (what gets hashed into the key) call, so the two can
    never disagree about what a question actually asked.
    """
    if question.criteria is not None:
        return (
            list(question.criteria)
            if isinstance(question.criteria, tuple)
            else dict(question.criteria)
        )
    if question.kind is Kind.NOUL:
        return {"true": "yes", "false": "no"}
    if question.kind is Kind.CHOICE:
        return {option: option for option in question.options}
    return list(SCORE_LEVELS[:question.levels]) if question.levels else list(SCORE_LEVELS)


def fingerprint(question: Question) -> str:
    """A canonical, stable serialisation of everything that determines
    this question's answer: its wording, its kind, its option/level
    shape, and the *resolved* criteria the client will actually send
    (not just ``question.criteria``, which may be unset and fall back to
    a shared default that can itself change).

    Used as the cache key's question component. Rewording
    ``SCORE_LEVELS``, or setting a per-question ``criteria`` override,
    changes this fingerprint for every question it affects and no
    other -- the same one-column-at-a-time invalidation the question
    text's hash already gives, extended to cover criteria too.

    ``json.dumps(..., sort_keys=True)`` keeps the result independent of
    dict insertion order, so the fingerprint -- and the hash built from
    it -- cannot depend on the platform's or the caller's iteration
    order.
    """
    payload = {
        "text": question.text,
        "kind": str(question.kind),
        "options": list(question.options),
        "levels": question.levels,
        "criteria": resolved_criteria(question),
    }
    return json.dumps(payload, sort_keys=True)


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

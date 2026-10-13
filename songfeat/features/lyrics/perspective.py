"""How strongly gender is cast, and what it would cost to adapt.

The teacher's question is not "what gender is this song" but "can I
adapt this for my student, and how much work is it". A student may be
uncomfortable singing to a specifically gendered love interest, or from
a specifically gendered perspective; sometimes a pronoun swap fixes it
and sometimes it cannot be fixed at all. So this axis reports
MECHANISMS, because mechanisms have different adaptation costs, and
names the one that set the cost.

Two subjects, only one of them gated. Narrator casting always applies.
The love-interest columns are null unless the song has a relational
focus -- which is what keeps a song with incidental gendered passers-by
quiet: they are not the song's focus, so there is nothing to be
undefined about. Gating on relational focus rather than on romance also
catches a lullaby to a son, which a teacher may filter for the same
reason though nothing romantic is happening.

``narrator_gender`` and ``love_interest_gender`` report the gender the
TEXT casts, nothing else. Where performance tradition assigns a role to
a different voice -- a boy sung by a mezzo, a trouser role -- that is
catalogue metadata, not readable from the text, and is out of scope
here.
"""

from __future__ import annotations

from typing import Any

from ...model import Part, Piece
from ..base import feature
from .questions import Answer, Kind, Question, register
from .service import classify_part, error_summary
from .vocabulary import CAST_MECHANISMS, CAST_QUESTIONS, GENDERS

#: Subject slug, and the description substituted into its questions.
#: The description comes from our own constants here, never from a
#: lyric -- the fixed-question-text rule is about input, not templating.
SUBJECTS: tuple[tuple[str, str], ...] = (
    ("narrator", "the person singing this text"),
    ("love_interest", "the person this text centres on or is addressed to"),
)

#: A probability at or above this counts as established.
FIRES = 0.5

#: The relational-focus gate. Only the love_interest columns are gated
#: on it; narrator casting is never gated (see module docstring).
_GATE = "relational_focus_present"


def _build() -> tuple[tuple[Question, ...], tuple[str, ...]]:
    questions: list[Question] = []
    fields: list[str] = []
    for subject, description in SUBJECTS:
        gender_column = f"{subject}_gender"
        questions.append(Question(
            id=gender_column, kind=Kind.CHOICE,
            text=f"What is the gender of {description}, as the text casts it?",
            column=gender_column, axis="perspective", options=GENDERS,
        ))
        fields.extend([gender_column, f"{subject}_gender_cast"])
        for mechanism, _cost in CAST_MECHANISMS:
            column = f"{subject}_cast_by_{mechanism}"
            questions.append(Question(
                id=column, kind=Kind.NOUL,
                text=(
                    f"Considering the gender of {description}: "
                    f"{CAST_QUESTIONS[mechanism]}"
                ),
                column=column, axis="perspective",
            ))
            fields.append(column)
        if subject == "narrator":
            for column, text in (
                (_GATE, "Does this text centre on, or address, one specific other person?"),
                ("relationship_is_romantic",
                 "Is the relationship in this text romantic or intimate?"),
                ("addressee_present", "Is this text addressed to someone, rather than about them?"),
            ):
                questions.append(Question(
                    id=column, kind=Kind.NOUL, text=text,
                    column=column, axis="perspective",
                ))
                fields.append(column)
    fields.extend(["gender_adaptation_cost", "gender_adaptation_blocker"])
    return tuple(questions), tuple(fields)


QUESTIONS, PERSPECTIVE_FIELDS = _build()
register(QUESTIONS)


def _choice_or_none(answer: Answer | None) -> str | None:
    """A Choice answer's value, or None if it is missing, erroring, or
    outside the declared option set.

    An unrecognised value must never be coerced to "unspecified":
    "unspecified" is a real answer ("the text does not say"), and
    coercing a value we don't understand into it would misreport an
    anomaly as a genuine classification.
    """
    if answer is None or answer.error or answer.choice is None:
        return None
    if answer.choice not in GENDERS:
        return None
    return answer.choice


def cast_score(
    answers: dict[str, Answer], subject: str
) -> tuple[int | None, str | None]:
    """The 0-5 adaptation cost for one subject, and the mechanism that
    set it, or (None, None) unless ALL FIVE mechanisms were answered.

    An int, not a float: the value is a lookup into CAST_MECHANISMS'
    five integer costs, never a model-returned probability-weighted
    mean, so it can only ever land on 0, 1, 3, 4 or 5 -- a float would
    advertise a precision (3.5?) the derivation cannot produce.

    ALL FIVE, ALWAYS -- the same all-or-nothing precondition
    ``age.band_from`` applies to its nine inputs, and for a stronger
    reason. The cost is a MAX, so a mechanism with no answer can only
    make it come out too LOW: with ``named_role`` and ``biology``
    missing, a text that is not adaptable at all reported
    ``gender_adaptation_cost = 1, blocker = "pronouns"``, i.e. "swap
    the pronouns and you're done", with nothing in the row saying
    anything had been missed. That is the first driving use case --
    "the teacher needs to know which, before assigning the song" --
    answered backwards. A lean ``core`` run showed the same thing in
    real output: it asks only ``pronouns`` of the five, and all three
    songs came back cost 0, blocker null, which reads as "nothing to
    change".

    So an under-informed cost is not reported as a cost. A real 0
    (all five answered, none established) still means "nothing was
    cast"; None means "we did not read enough to say". Ties at equal
    cost break by CAST_MECHANISMS order, which is documented in
    vocabulary.py rather than left incidental.
    """
    worst_cost = 0
    blocker: str | None = None
    for mechanism, cost in CAST_MECHANISMS:
        answer = answers.get(f"{subject}_cast_by_{mechanism}")
        if answer is None or answer.error or answer.probability is None:
            return None, None
        if answer.probability >= FIRES and cost > worst_cost:
            worst_cost, blocker = cost, mechanism
    return worst_cost, blocker


def columns_from(answers: dict[str, Answer]) -> dict[str, Any]:
    """Map answers to columns. Pure; unasked questions stay None."""
    out: dict[str, Any] = {name: None for name in PERSPECTIVE_FIELDS}

    for column in (_GATE, "relationship_is_romantic", "addressee_present"):
        answer = answers.get(column)
        out[column] = (
            answer.probability if answer and not answer.error else None
        )

    gate = out[_GATE]
    gated_open = gate is not None and gate >= FIRES

    # One entry per subject that applies to this song, in SUBJECTS
    # order. A None entry is a subject whose cost could not be
    # established, which the derived cost must respect rather than
    # quietly maximise over what happens to be present.
    costs: list[tuple[int, str | None] | None] = []
    for subject, _description in SUBJECTS:
        if subject == "love_interest" and not gated_open:
            # Null, not 0.0: with no relational focus there is no
            # beloved whose gender could be cast, so "not cast" would
            # be an answer to a question that does not arise. Not a
            # missing answer either -- the subject does not apply, so
            # it contributes nothing to the cost and does not block it.
            continue
        out[f"{subject}_gender"] = _choice_or_none(answers.get(f"{subject}_gender"))
        for mechanism, _cost in CAST_MECHANISMS:
            column = f"{subject}_cast_by_{mechanism}"
            answer = answers.get(column)
            out[column] = (
                answer.probability if answer and not answer.error else None
            )
        score, blocker = cast_score(answers, subject)
        out[f"{subject}_gender_cast"] = score
        costs.append(None if score is None else (score, blocker))

    if costs and all(entry is not None for entry in costs):
        worst = max(cost for cost, _blocker in costs)
        out["gender_adaptation_cost"] = worst
        # Ties break by SUBJECTS order, so the narrator wins an equal
        # cost: the narrator's casting is the one that always applies
        # (it is never gated), so it is the one a teacher is always
        # entitled to see named.
        out["gender_adaptation_blocker"] = next(
            blocker for cost, blocker in costs if cost == worst
        )
    return out


@feature(
    name="lyrics_perspective", group="lyrics", scope="part", source="songfeat",
    description=(
        "How strongly the text casts the gender of the singer and of the "
        "person the song centres on, and what adapting it would cost. "
        "``*_cast_by_*`` are the mechanisms -- pronouns (cheap to swap), a "
        "gendered term of address, gendered grammar, a named dramatic "
        "character, or a biological detail (not adaptable). "
        "``gender_adaptation_cost`` is 0-5, the worse of the two subjects, "
        "and ``gender_adaptation_blocker`` names the mechanism that set "
        "it -- both null unless every mechanism they read was answered, "
        "because the cost is a maximum and a missing mechanism could "
        "only make it read too low ('swap the pronouns' for a text that "
        "cannot be adapted at all). The love-interest columns are null unless the song has a "
        "relational focus: a text with incidental gendered people in it "
        "has no beloved whose gender could be cast. Gender is as the TEXT "
        "casts it; where performance tradition assigns a role to another "
        "voice -- a boy sung by a mezzo, a trouser role -- that is "
        "catalogue metadata and is not readable here."
    ),
    fields=PERSPECTIVE_FIELDS,
    best_with=("musicxml",),
    # The one opt-in group: it is neither offline nor free, so an
    # unfiltered run leaves it out entirely (see FeatureSpec.opt_in).
    opt_in=True,
)
def lyrics_perspective(part: Part, piece: Piece) -> dict[str, Any]:
    classification = classify_part(part, piece)
    if classification.reason is not None:
        return {name: None for name in PERSPECTIVE_FIELDS}
    out = columns_from(classification.answers)
    # A question that came back as an error nulls its own column; its
    # reason goes to the record's error channel rather than being
    # dropped, which would leave a null nothing in the row explains.
    failures = error_summary(classification.answers, PERSPECTIVE_FIELDS)
    if failures is not None:
        out["_errors"] = {"lyrics_perspective": failures}
    return out

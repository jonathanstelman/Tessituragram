"""The one seam every axis feature uses to reach the classifier.

Features take ``(part, piece)`` and nothing else -- that is the
registry's contract -- so the configured client reaches them through
module state rather than through an argument. ``configure()`` is called
once by the CLI; until it is, every axis reports null with
NOT_CONFIGURED as the reason.

Answers are memoised on the normalised text's hash, so the eight axis
features that each want the same part's classification cost one
classification between them -- not eight.
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import dataclass, field

from ...model import Part, Piece
from .assemble import assemble_text
from .cache import AnswerCache
from .client import CHARS_PER_TOKEN, MISSING_KEY  # noqa: F401  (MISSING_KEY re-exported for the CLI)
from .questions import Answer, Kind, Question, SET_VERSIONS, question_set

#: The model's context window, in tokens. State longer than this is
#: refused rather than truncated. Shares ``client.CHARS_PER_TOKEN`` --
#: not a private copy of the same number -- so this threshold can never
#: silently disagree with what ``--lyrics-estimate`` predicts.
MAX_STATE_TOKENS = 64000

NOT_CONFIGURED = (
    "no classifier is configured; set JEV_KEY and request the 'lyrics' "
    "group to populate these columns"
)
NO_LYRICS = (
    "this part carries no lyric events; lyric features need a "
    "lyric-bearing format such as MusicXML"
)
EMPTY_AFTER_REASSEMBLY = (
    "this part's lyrics reassembled to {word_count} word(s) across "
    "{verse_count} verse(s) of nothing but blank text; there is no song "
    "here to classify"
)
TEXT_TOO_LONG = (
    "the lyric text exceeds the model's context window, so it was "
    "refused rather than truncated: a classification of the first part of "
    "a song must not be reported as a classification of the song"
)


@dataclass(frozen=True)
class Classification:
    """Answers, or the one reason there are none.

    Always returned -- never ``None`` -- so a caller branches on
    ``reason`` rather than on the object's existence.
    """

    answers: dict[str, Answer] = field(default_factory=dict)
    model: str | None = None
    question_set: str | None = None
    classified_at: str | None = None
    reason: str | None = None


_client = None
_cache: AnswerCache | None = None
_set_name = "full"
_unavailable_reason: str | None = None
_memo: dict[str, Classification] = {}


def configure(client=None, cache: AnswerCache | None = None,
              question_set_name: str = "full",
              unavailable_reason: str | None = None) -> None:
    """Point the service at a client, or record why there isn't one.

    ``unavailable_reason`` is for the caller that already knows *why*
    ``client`` is ``None`` -- e.g. the CLI, which can tell "no JEV_KEY"
    (``client.MISSING_KEY``) apart from "the group was never requested".
    Without it, ``classify_part`` falls back to the generic
    ``NOT_CONFIGURED``, which is the right reason only for the second
    case.
    """
    global _client, _cache, _set_name, _unavailable_reason
    _client, _cache, _set_name = client, cache, question_set_name
    _unavailable_reason = unavailable_reason
    _memo.clear()


def reset() -> None:
    configure(None, None, "full", None)


def is_configured() -> bool:
    return _client is not None


def _validate(question: Question, answer: Answer) -> Answer:
    """Reject an answer that does not fit its question's declared type.

    A Choice outside the option set is NOT coerced to "unspecified":
    that is a real answer meaning the text does not say, and a model
    returning something unexpected is a different fact.
    """
    if answer.error:
        return answer
    if question.kind is Kind.CHOICE and answer.choice not in question.options:
        return Answer(question.id,
                      error=f"answer {answer.choice!r} is not a declared option")
    if question.kind is Kind.SCORE and answer.score is None:
        return Answer(question.id, error="no score returned")
    if question.kind is Kind.NOUL and answer.probability is None:
        return Answer(question.id, error="no probability returned")
    return answer


def classify_part(part: Part, piece: Piece) -> Classification:
    """This part's answers, or a Classification carrying only a reason."""
    if _client is None:
        return Classification(reason=_unavailable_reason or NOT_CONFIGURED)

    assembled = assemble_text(part)
    if assembled is None:
        return Classification(reason=NO_LYRICS)
    if not assembled.text:
        # A syllable of pure whitespace survives assemble_text's own
        # "no lyrics at all" check -- it is a non-empty string -- so it
        # reaches here as a real, but blank, LyricText. Distinct from
        # NO_LYRICS (no lyric *events* were ever found) and from a
        # column simply outside the active question set: here lyrics
        # were present in the source and reassembly produced nothing to
        # send to the classifier.
        return Classification(reason=EMPTY_AFTER_REASSEMBLY.format(
            word_count=assembled.word_count, verse_count=assembled.verse_count,
        ))
    if len(assembled.text) // CHARS_PER_TOKEN > MAX_STATE_TOKENS:
        return Classification(reason=TEXT_TOO_LONG)

    if assembled.sha256 in _memo:
        return _memo[assembled.sha256]

    questions = question_set(_set_name)
    today = _datetime.date.today().isoformat()
    answers: dict[str, Answer] = {}
    dates: list[str] = []
    to_ask: list[Question] = []

    for question in questions:
        hit = _cache.get(assembled.sha256, _client.model, question) if _cache else None
        if hit is None:
            to_ask.append(question)
        else:
            answer, when = hit
            answers[question.id] = answer
            dates.append(when)

    if to_ask:
        by_id = {question.id: question for question in to_ask}
        for answer in _client.ask(assembled.text, to_ask):
            validated = _validate(by_id[answer.question_id], answer)
            answers[answer.question_id] = validated
        if _cache:
            _cache.put_many(
                assembled.sha256, _client.model,
                [(question, answers[question.id]) for question in to_ask],
                today,
            )
        dates.append(today)

    result = Classification(
        answers=answers,
        model=_client.model,
        question_set=SET_VERSIONS[_set_name],
        # The oldest contributing date, so provenance describes when
        # these answers were actually made rather than when they were
        # last read out of the cache.
        classified_at=min(dates) if dates else today,
        reason=None,
    )
    _memo[assembled.sha256] = result
    return result

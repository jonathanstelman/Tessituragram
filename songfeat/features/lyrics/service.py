"""The one seam every axis feature uses to reach the classifier.

Features take ``(part, piece)`` and nothing else -- that is the
registry's contract -- so the configured client reaches them through
module state rather than through an argument. ``configure()`` is called
once by the CLI; until it is, every axis reports null with
NOT_CONFIGURED as the reason.

Answers are memoised on the normalised text's hash, so the eight axis
features that each want the same part's classification cost one
classification between them -- not eight. A FAILED classification is
memoised too, and for the same reason: an exception that is not
remembered is an exception raised, and paid for, eight times. Before
that was fixed a single raising client cost 7 ``ask()`` calls for one
part -- up to 56 HTTP calls per song on a full run -- and still
reported no reason at all.

``error_summary`` is the other half of not losing a reason: an answer
that came back as an error nulls its own column, and the axis reports
*why* through the record's error channel rather than leaving a bare
``None``.
"""

from __future__ import annotations

import datetime as _datetime
import os
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
CLASSIFICATION_FAILED = (
    "the lyric classifier could not be reached or did not answer: {detail}"
)
REDACTED = "[redacted]"
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


def error_summary(answers: dict[str, Answer],
                  fields: tuple[str, ...]) -> str | None:
    """One line naming every question of this axis that failed, and why.

    ``Answer.error`` carries the only account of a partial failure
    there is -- "HTTP 503", "no score returned", "answer 'androgynous'
    is not a declared option" -- and the spec requires an API failure's
    reason to carry the status and an unparseable answer's reason to
    name the question. Every axis used to map such an answer to a bare
    ``None`` and drop the error, which left a null with no reason
    anywhere in the row. The axes now hand this string to the record's
    error channel (``_errors``), the same one ``pipeline`` already uses
    for a failed sidecar write, so it surfaces as ``_error_<axis>``.

    One entry per axis rather than one per question: 153 questions must
    not be able to add 153 columns to a table. Returns ``None`` when
    nothing failed, so a caller can skip the key entirely.

    Ordered by ``fields``, not by dict order, so the same failures
    always produce the same string -- a reason column that reshuffles
    between runs is a diff nobody can read.
    """
    failed = [
        (column, answers[column].error)
        for column in fields
        if column in answers and answers[column].error
    ]
    if not failed:
        return None
    detail = "; ".join(f"{column}: {error}" for column, error in failed)
    return f"{len(failed)} question(s) failed: {detail}"


def _scrub(text: str) -> str:
    """The same text with the API key removed, if it is in there.

    The key is read once from the environment and goes in a header; no
    code here puts it anywhere else. This is the belt to that braces:
    ``failure_reason`` is built from an exception raised by code we do
    not own (httpx, the SDK, the server's own message), the reason it
    builds lands in a user-visible column, and a key that reached a CSV
    could not be un-leaked. Cheap, and it cannot be wrong in the
    dangerous direction.
    """
    key = os.environ.get("JEV_KEY")
    return text.replace(key, REDACTED) if key else text


def failure_reason(exc: BaseException) -> str:
    """The user-visible reason for a classification that raised.

    Names the exception type and its message, because "something went
    wrong" in a reason column is no better than the null reason this
    replaces -- a budget stop, a malformed response and a timeout need
    different actions from the person reading the row. Scrubbed of the
    API key (see ``_scrub``), and never carrying a traceback or a file
    path of ours.
    """
    detail = _scrub(f"{type(exc).__name__}: {exc}".strip().rstrip(":").strip())
    return CLASSIFICATION_FAILED.format(detail=detail)


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
        try:
            returned = _client.ask(assembled.text, to_ask)
        except Exception as exc:  # noqa: BLE001 - see below
            # Anything raised in here -- a budget stop, a malformed 200,
            # an httpx fault, a bug of ours -- becomes ONE failed
            # classification with a readable reason, MEMOISED like a
            # successful one. Without the memo each of the eight axis
            # features re-enters this function and re-attempts the
            # call, so one song cost seven more attempts (up to 56 HTTP
            # calls on a full run) and still reported a null reason.
            # Answers already paid for before the raise are banked on
            # the way out: BudgetExceeded carries them.
            _bank(assembled.sha256, to_ask, getattr(exc, "answers", ()), today)
            return _remember(assembled.sha256,
                             Classification(reason=failure_reason(exc)))

        by_id = {question.id: question for question in to_ask}
        for answer in returned:
            question = by_id.get(answer.question_id)
            if question is None:
                # An id we never asked about. No column reads it, but it
                # is kept (as an error, never as a value) rather than
                # raising KeyError and nulling all 178 columns over one
                # stray key.
                answers[answer.question_id] = Answer(
                    answer.question_id,
                    error="the classifier answered a question that was not asked",
                )
                continue
            answers[answer.question_id] = _validate(question, answer)
        for question in to_ask:
            # A question the client omitted entirely: its own column
            # nulls with its own reason, exactly as a batch failure
            # does, instead of a KeyError taking the group down.
            answers.setdefault(question.id, Answer(
                question.id,
                error="the classifier returned no answer for this question",
            ))
        if _cache:
            resolved = getattr(_client, "resolved_model", None)
            if resolved:
                # Before the write, so a roll-forward discards the old
                # version's rows and this batch lands in the clear.
                _cache.note_resolved_model(_client.model, resolved)
            _cache.put_many(
                assembled.sha256, _client.model,
                [(question, answers[question.id]) for question in to_ask],
                today,
            )
        dates.append(today)

    result = Classification(
        answers=answers,
        # The concrete model that answered, when the server reported
        # one; the alias we asked with only as a fallback. An alias
        # cannot tell two databases built a year apart apart.
        model=getattr(_client, "resolved_model", None) or _client.model,
        question_set=SET_VERSIONS[_set_name],
        # The oldest contributing date, so provenance describes when
        # these answers were actually made rather than when they were
        # last read out of the cache.
        classified_at=min(dates) if dates else today,
        reason=None,
    )
    return _remember(assembled.sha256, result)


def _remember(text_hash: str, result: Classification) -> Classification:
    """Memoise one part's classification -- success OR failure.

    Memoising the failure is the point: eight axis features ask for the
    same part's classification, and a failure that is not remembered is
    a failure attempted eight times.
    """
    _memo[text_hash] = result
    return result


def _bank(text_hash: str, asked, answers, when: str) -> None:
    """Cache whatever completed before a failure propagated.

    Those answers were paid for. ``put_many`` drops errored ones, so
    only real answers land. Silent when there is no cache or nothing
    completed.
    """
    if _cache is None or not answers:
        return
    by_id = {question.id: question for question in asked}
    pairs = [
        (by_id[answer.question_id], answer)
        for answer in answers
        if answer.question_id in by_id
    ]
    if pairs:
        _cache.put_many(text_hash, _client.model, pairs, when)

"""Talking to the classifier.

Wire format (checked against https://docs.typesafe.ai and the live
endpoint on 2026-10-12, with a single real request per question kind --
see the module's confirmation notes below and the task report for the
exact curl output):

A single POST to ``https://api.typesafe.ai/v1/systemone`` carries
``model``, ``state`` (the lyric text) and ``questions``, a map of
question id to a typed question object. Each question object uses
``type`` as its discriminator (``"noul"``, ``"choice"`` or ``"score"``),
``instructions`` for the question text, and ``criteria`` -- for
``noul``/``choice`` a ``{answer: description}`` map, for ``score`` an
ordered list of level descriptions. The response carries ``answers``, a
map of question id to its typed answer: ``{"type": "noul", "noul":
<probability>}``, ``{"type": "choice", "choice": <option>, "confidence":
<float>, "probabilities": {...}}``, or ``{"type": "score", "score":
<float>, "confidence": <float>, "legend": {...}, "probabilities": {...}}``.

Batching matters: one call carrying many questions sends the state once,
and TypeSafe's own cookbook (``cookbooks/parallel_questions``) measures a
batched call at 12.2x cheaper and 10x faster than the same questions sent
singly ("one call, all 13" at $0.000497 versus "13 calls, one each" at
$0.006090).

**What was confirmed, and how:**

- ``Score`` returns the probability-weighted mean directly, in a
  ``score`` field, alongside ``legend`` (level descriptions) and
  ``probabilities`` (the full distribution) and ``confidence``. The
  docs' own words (``api.md``): "The probability-weighted answer across
  the levels; can land between levels." A live call against a 4-level
  score question returned ``{"score": 0.06, "probabilities": {"0": 0.94,
  "1": 0.06, "2": 0.0, "3": 0.0}, ...}`` -- the mean of a distribution
  that is 94% mass on level 0, exactly as the docs describe. So
  ``_parse_answer`` below just reads ``score`` -- there is no mean to
  compute here, the API already did it. **Confirmed**, by docs and by a
  live call.
- The questions-per-call cap of 20 (``questions.BATCH_LIMIT``) could
  **not** be confirmed in the reachable docs (``api.md``,
  ``patterns/fan-out.md``, ``cookbooks/parallel_questions.md``,
  ``sdk/python/api/exceptions.md``): none of them states a maximum, and
  none of the documented exceptions is a batch-size validation error.
  It **was** confirmed live, after fix-round review: a batch of exactly
  20 trivial Noul questions sent in one call to this endpoint came back
  with all 20 answered cleanly in that single call (see
  ``test_the_real_api_accepts_a_full_batch_of_twenty``). That rules out
  the one failure mode that matters -- a real cap *below* 20, which
  would silently break every full run -- without claiming the real cap
  isn't higher (which would only mean room to batch more, not a bug).
- What was *not* anticipated by the plan, and was only found by making a
  real call (the request shape above assumed by an earlier draft of
  this module used ``kind``/``text``/``options``/``levels`` and a bare
  ``probability`` field, and ``DEFAULT_MODEL``/``DEFAULT_BASE_URL``
  pointed at a nonexistent ``model`` and a 404 path): the discriminator
  is ``type`` not ``kind``, the question text field is ``instructions``
  not ``text``, a ``criteria`` field is mandatory (a 400 reads "Noul
  question must have criteria or instructions" when it is missing), the
  live model string is ``"jev-latest"`` (which resolves server-side to
  ``"jev-1.13.0"``) rather than ``"typesafe/jev-1.13"``, and the base
  path is ``/v1/systemone`` rather than ``/provider/v1/systemone``. All
  of this was corrected below against the live response; see the task
  report for the exact exchanges.

``_payload`` and ``_parse_answer`` are the only two functions that know
the wire format.

**``criteria`` and the shared Score rubric (fix round 1).** The live API
requires a ``criteria`` field: a ``{answer: description}`` map for Noul
and Choice, an ordered list of level descriptions for Score. For
Noul/Choice a generic criteria map is harmless, because the question
text already carries the judgment and the option names are
self-describing. For Score it is not harmless: the derived age band
tests Score outputs against absolute thresholds (``advisory_sex >= 3``,
``advisory_violence >= 4``, ...), which only mean something if "3" is
the same severity on every call. So every Score question defaults to
``questions.SCORE_LEVELS``, one shared, dimension-neutral 0-5 rubric,
rather than a per-question placeholder the model would otherwise invent
differently each time. This is the v1 approach; ``Question.criteria`` is
the seam for a later task to give an individual question its own
rubric, overriding the shared default, without reshaping anything here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, Sequence

from .questions import BATCH_LIMIT, Answer, Kind, Question, resolved_criteria

if TYPE_CHECKING:
    import httpx

DEFAULT_MODEL = "jev-latest"
DEFAULT_BASE_URL = "https://api.typesafe.ai/v1/systemone"

MISSING_KEY = (
    "no JEV_KEY is set, so the lyric classifier was not called; see the "
    "README for what the key is for and what it costs"
)

#: Rough characters per token, for the estimate only. Deliberately
#: crude: an estimate that needs a tokeniser is one nobody runs.
CHARS_PER_TOKEN = 4


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Estimate:
    calls: int
    questions: int
    input_tokens: int


class JevClient(Protocol):
    model: str
    calls_made: int

    def ask(self, state: str, questions: Sequence[Question]) -> list[Answer]: ...


def _batches(questions: Sequence[Question]) -> list[list[Question]]:
    return [
        list(questions[start:start + BATCH_LIMIT])
        for start in range(0, len(questions), BATCH_LIMIT)
    ]


def estimate(questions: Sequence[Question], state: str) -> Estimate:
    """What a run would cost, without making it."""
    batches = _batches(questions)
    state_tokens = len(state) // CHARS_PER_TOKEN
    question_tokens = sum(len(q.text) for q in questions) // CHARS_PER_TOKEN
    return Estimate(
        calls=len(batches),
        questions=len(questions),
        input_tokens=state_tokens * len(batches) + question_tokens,
    )


def _payload(state: str, batch: Sequence[Question]) -> dict[str, Any]:
    questions: dict[str, Any] = {}
    for question in batch:
        questions[question.id] = {
            "type": str(question.kind),
            "instructions": question.text,
            # Resolved in questions.py, not here, so the cache (which
            # hashes this same resolution into its key) and the client
            # can never disagree about what a question actually asked.
            "criteria": resolved_criteria(question),
        }
    return {"state": state, "questions": questions}


def _parse_answer(question: Question, raw: dict[str, Any] | None) -> Answer:
    if raw is None:
        return Answer(question.id, error="no answer returned for this question")
    confidence = raw.get("confidence")
    if question.kind is Kind.NOUL:
        return Answer(question.id, probability=raw.get("noul"),
                      confidence=confidence)
    if question.kind is Kind.SCORE:
        return Answer(question.id, score=raw.get("score"), confidence=confidence)
    return Answer(question.id, choice=raw.get("choice"), confidence=confidence)


class HttpJevClient:
    def __init__(
        self, api_key: str, model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL, max_calls: int | None = None,
        max_retries: int = 2, transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        # httpx is an optional dependency -- the same pattern as gspread in
        # songfeat/sinks/sheets.py: importing this module (and importing
        # songfeat generally) must not require it, so the import happens
        # here, inside the constructor, not at module level.
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - exercised by hand
            raise ImportError(
                "HttpJevClient needs the optional HTTP client. "
                "Install it with: pip install httpx"
            ) from exc
        self._httpx = httpx
        self.model = model
        self.max_calls = max_calls
        self.max_retries = max_retries
        self.calls_made = 0
        self._base_url = base_url
        # The key goes in a header and nowhere else: never a log line,
        # never an error message, never a reason column.
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport, timeout=timeout,
        )

    def ask(self, state: str, questions: Sequence[Question]) -> list[Answer]:
        answers: list[Answer] = []
        for batch in _batches(questions):
            if self.max_calls is not None and self.calls_made >= self.max_calls:
                raise BudgetExceeded(
                    f"stopping after {self.max_calls} calls; raise "
                    f"--lyrics-max-calls or narrow the inputs"
                )
            answers.extend(self._ask_one(state, batch))
        return answers

    def _ask_one(self, state: str, batch: Sequence[Question]) -> list[Answer]:
        last: str = "no attempt was made"
        for attempt in range(self.max_retries + 1):
            self.calls_made += 1
            try:
                response = self._client.post(
                    self._base_url,
                    json={"model": self.model, **_payload(state, batch)},
                )
            except self._httpx.HTTPError as error:
                last = f"{type(error).__name__}"
            else:
                if response.status_code == 200:
                    returned = response.json().get("answers", {})
                    return [
                        _parse_answer(question, returned.get(question.id))
                        for question in batch
                    ]
                last = f"HTTP {response.status_code}"
                if response.status_code < 500 and response.status_code != 429:
                    break
            if attempt < self.max_retries:
                time.sleep(0.2 * (2 ** attempt))
        return [Answer(question.id, error=last) for question in batch]


class FakeJevClient:
    """Answers from a script. Unscripted questions report an error.

    Not a zero: a test that silently gets 0.0 for a question it forgot
    to script is a test that passes for the wrong reason.
    """

    def __init__(self, scripted: dict[str, Answer], model: str = "fake/jev-1") -> None:
        self.model = model
        self.scripted = scripted
        self.calls_made = 0

    def ask(self, state: str, questions: Sequence[Question]) -> list[Answer]:
        self.calls_made += len(_batches(questions))
        return [
            self.scripted.get(
                question.id,
                Answer(question.id, error="not scripted in this test"),
            )
            for question in questions
        ]

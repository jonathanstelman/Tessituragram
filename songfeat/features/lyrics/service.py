"""The one seam every axis feature uses to reach the classifier.

Features take ``(part, piece)`` and nothing else -- that is the
registry's contract -- so the configured client reaches them through
this module rather than through an argument. ``configure()`` is called
once by the CLI; until it is, ``classify_part`` returns a
``Classification`` with ``NOT_CONFIGURED`` as its reason and every axis
reports null.

Answers are memoised per normalised-text hash, so the eight axis
features that each ask for the same part's classification cost one
classification between them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...model import Part, Piece
from .questions import Answer

NOT_CONFIGURED = (
    "no classifier is configured; set JEV_KEY and request the 'lyrics' "
    "group to populate these columns"
)


@dataclass(frozen=True)
class Classification:
    """Answers, or the one reason there are none.

    Always returned -- never None -- so a caller branches on ``reason``
    rather than on the object's existence. Task 11 fills the body; this
    shape is fixed here so Tasks 5-8 can be written and reviewed against
    it and need no edit later.
    """

    answers: dict[str, Answer] = field(default_factory=dict)
    model: str | None = None
    question_set: str | None = None
    classified_at: str | None = None
    reason: str | None = None


def classify_part(part: Part, piece: Piece) -> Classification:
    return Classification(reason=NOT_CONFIGURED)

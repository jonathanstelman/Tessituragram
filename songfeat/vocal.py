"""Identify which part carries the sung line.

Returns the evidence alongside the score so that a wrong guess can be
inspected rather than silently believed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .context import PartContext
from .model import Part, Piece

#: Generous outer bounds of the human singing range, in MIDI numbers (E2-C6).
VOCAL_LOW, VOCAL_HIGH = 40, 84

#: Instrument or part names that indicate singing.
VOCAL_WORDS = ("voice", "vocal", "soprano", "alto", "tenor", "bass",
               "baritone", "mezzo", "sing", "chant")

#: How much each signal contributes. They sum to 1.0.
WEIGHTS = {"lyrics": 0.45, "monophony": 0.25, "range": 0.20, "naming": 0.10}


@dataclass
class VocalEvidence:
    confidence: float
    is_candidate: bool
    signals: dict[str, float] = field(default_factory=dict)


def _range_score(part: Part) -> float:
    """Fraction of notes inside the plausible singing range."""
    inside = sum(1 for n in part.notes if VOCAL_LOW <= n.midi <= VOCAL_HIGH)
    return inside / len(part.notes)


def _naming_score(part: Part) -> float:
    # Match only if a name or instrument field is exactly a single vocal keyword,
    # avoiding false matches on compound names like "Bass Clarinet".
    name_lower = (part.name or "").strip().lower()
    instrument_lower = (part.instrument or "").strip().lower()

    if name_lower in VOCAL_WORDS or instrument_lower in VOCAL_WORDS:
        return 1.0
    return 0.0


def detect_vocal(part: Part, piece: Piece) -> VocalEvidence:
    if part.is_empty:
        return VocalEvidence(
            confidence=0.0,
            is_candidate=False,
            signals={"lyrics": 0.0, "monophony": 0.0, "range": 0.0, "naming": 0.0}
        )

    context = PartContext(part, piece)
    signals = {
        "lyrics": 1.0 if any(n.lyric for n in part.notes) else 0.0,
        "monophony": len(context.monophonic) / len(part.notes),
        "range": _range_score(part),
        "naming": _naming_score(part),
    }
    confidence = sum(WEIGHTS[k] * v for k, v in signals.items())
    return VocalEvidence(
        confidence=round(confidence, 4),
        is_candidate=confidence >= 0.5,
        signals=signals,
    )

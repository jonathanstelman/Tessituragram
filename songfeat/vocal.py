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

#: Unambiguous vocal keywords (never instrument qualifiers).
#: Match as whole words anywhere in the field.
UNAMBIGUOUS_VOCAL_WORDS = (
    "voice", "vocal", "soprano", "mezzo", "baritone", "sing", "chant",
    "canto", "voce",  # Italian aria repertoire
)

#: Ambiguous vocal keywords (also instrument qualifiers: Bass Clarinet, Alto Saxophone).
#: Match only when other tokens are decorations (numbers, roman numerals, or decoration words).
AMBIGUOUS_VOCAL_WORDS = ("bass", "alto", "tenor")

#: Words that decorate ambiguous vocal keywords (part numbers, roles, etc.).
DECORATION_WORDS = ("solo", "voice", "vocal", "part", "line")

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


def _is_decoration(token: str) -> bool:
    """Check if a token is a decoration (number, roman numeral, or specific word)."""
    if token in DECORATION_WORDS:
        return True
    if token.isdigit():
        return True
    # Roman numeral: uppercase or lowercase i, v, x, l, c, d, m
    if re.match(r"^[ivxlcdm]+$", token):
        return True
    return False


def _naming_score(part: Part) -> float:
    """Match vocal keywords with intelligence about ambiguous instrument qualifiers.

    Unambiguous keywords (voice, vocal, soprano, etc.) match as whole words anywhere.
    Ambiguous keywords (bass, alto, tenor) match only if other tokens are decorations
    (numbers, roman numerals, or words like solo/voice/vocal/part/line).
    """
    name_lower = (part.name or "").strip().lower()
    instrument_lower = (part.instrument or "").strip().lower()

    for field in [name_lower, instrument_lower]:
        if not field:
            continue

        # Tokenise on whitespace and hyphens
        tokens = [t for t in re.split(r"[\s\-]+", field) if t]

        # Check for unambiguous words (can match as a whole word anywhere)
        if any(word in UNAMBIGUOUS_VOCAL_WORDS for word in tokens):
            return 1.0

        # Check for ambiguous words (only match if other tokens are decorations)
        for token in tokens:
            if token in AMBIGUOUS_VOCAL_WORDS:
                # Check if all other tokens are decorations
                other_tokens = [t for t in tokens if t != token]
                if all(_is_decoration(t) for t in other_tokens):
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

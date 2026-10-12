"""The age band: child / adolescent / adult, derived not asked.

Bands rather than a numeric age because nothing in this project's
validation data could justify the difference between 13 and 14. Common
Sense Media reaches numeric floors through trained reviewers applying
developmental guidelines we are not applying; borrowing the number would
look more precise than it is.

The band MAY NEVER DEFAULT, in either direction. A reassuring "child"
about a song nobody read is the one genuinely harmful output this design
could produce. A conservative "adult" is not the safe alternative: it
would quietly hide most of the repertoire from the people this is for.
Any missing advisory makes the band null.
"""

from __future__ import annotations

from typing import Any

from ...model import Part, Piece
from ..base import feature
from .advisories import ADVISORY_FIELDS, DIMENSIONS
from .service import classify_part

RULE_VERSION = "v1"

AGE_FIELDS: tuple[str, ...] = ("age_band", "age_band_driver", "age_band_rule")

#: A modifier probability at or above this counts as holding.
FIRES = 0.5

#: (dimension, threshold, required modifier or None) -> adult
_ADULT: tuple[tuple[str, float, str | None], ...] = (
    ("sex", 3.0, None),
    ("violence", 4.0, "depicted"),
    ("self_harm", 2.0, "first_person"),
    ("substance_use", 3.0, None),
    ("language", 3.0, None),
)

#: ... -> adolescent
_ADOLESCENT: tuple[tuple[str, float, str | None], ...] = (
    ("sex", 1.0, None),
    ("violence", 2.0, None),
    ("death", 3.0, "first_person"),
    ("self_harm", 1.0, None),
    ("language", 1.0, None),
)


def _triggered(columns: dict[str, Any], rules: tuple[tuple[str, float, str | None], ...]):
    """Dimensions whose rule holds, in DIMENSIONS order."""
    hits = []
    for dimension, threshold, modifier in rules:
        intensity = columns.get(f"advisory_{dimension}")
        if intensity is None or intensity < threshold:
            continue
        if modifier is not None:
            flag = columns.get(f"advisory_{dimension}_{modifier}")
            if flag is None or flag <= FIRES:
                continue
        hits.append((dimension, intensity))
    return hits


def _driver(hits) -> str | None:
    """The highest-intensity triggering dimension; ties by DIMENSIONS order."""
    if not hits:
        return None
    highest = max(intensity for _dimension, intensity in hits)
    for dimension in DIMENSIONS:
        if any(d == dimension and i == highest for d, i in hits):
            return dimension
    return None


def band_from(columns: dict[str, Any]) -> dict[str, Any]:
    """Derive the band from already-computed advisory columns.

    Never defaults: if any of the 27 advisory columns is missing, the
    band, driver and (for consistency with the rest of this dict) are
    reported null -- only the rule version is always known, since it
    names the rule that was consulted, not its verdict.
    """
    if any(columns.get(field) is None for field in ADVISORY_FIELDS):
        return {"age_band": None, "age_band_driver": None,
                "age_band_rule": RULE_VERSION}

    for rules, band in ((_ADULT, "adult"), (_ADOLESCENT, "adolescent")):
        hits = _triggered(columns, rules)
        if hits:
            return {"age_band": band, "age_band_driver": _driver(hits),
                    "age_band_rule": RULE_VERSION}

    return {"age_band": "child", "age_band_driver": None,
            "age_band_rule": RULE_VERSION}


@feature(
    name="lyrics_age", group="lyrics", scope="part", source="songfeat",
    description=(
        "child / adolescent / adult, DERIVED from the advisory columns by "
        "rule v1 rather than asked of the model, with "
        "``age_band_driver`` naming the dimension that set it and "
        "``age_band_rule`` recording the rule version so a "
        "re-derivation is traceable. Bands rather than a numeric age "
        "because no validation data here could justify the difference "
        "between 13 and 14. NEVER DEFAULTS: any missing advisory makes "
        "the band null, in both directions -- a reassuring 'child' about "
        "an unread song is harmful, and a conservative 'adult' would hide "
        "most of the repertoire. Advisory: a teacher's judgment, not a "
        "rating."
    ),
    fields=AGE_FIELDS,
    best_with=("musicxml",),
)
def lyrics_age(part: Part, piece: Piece) -> dict[str, Any]:
    from .advisories import columns_from as advisory_columns

    classification = classify_part(part, piece)
    if classification.reason is not None:
        return {"age_band": None, "age_band_driver": None,
                "age_band_rule": RULE_VERSION}
    return band_from(advisory_columns(classification.answers))

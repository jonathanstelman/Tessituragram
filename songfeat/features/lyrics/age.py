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
Any missing advisory among the nine rule v1 actually reads makes the
band null; the other eighteen advisory columns are not preconditions,
so a batch failure elsewhere never nulls this one (see ``_RULE_INPUTS``
and ``band_from`` below for exactly which nine, and why).
"""

from __future__ import annotations

from typing import Any

from ...model import Part, Piece
from ..base import feature
from .advisories import DIMENSIONS
from .service import classify_part

RULE_VERSION = "v1"

AGE_FIELDS: tuple[str, ...] = ("age_band", "age_band_driver", "age_band_rule")

#: Exactly the nine advisory columns rule v1 reads: the five
#: dimensions it gates on (sex, violence, self_harm, substance_use,
#: language) plus death, and the three modifiers (violence_depicted,
#: self_harm_first_person, death_first_person) those gates consult.
#: positive_messages, role_models and religious_content -- and every
#: modifier column no clause reads, such as advisory_sex_depicted --
#: are deliberately NOT inputs, and must stay out of this set: one
#: failed batch nulls only its own columns, never a sibling axis's, so
#: this precondition must name only what the rule actually touches.
_RULE_INPUTS: tuple[str, ...] = (
    "advisory_sex",
    "advisory_violence", "advisory_violence_depicted",
    "advisory_self_harm", "advisory_self_harm_first_person",
    "advisory_substance_use",
    "advisory_language",
    "advisory_death", "advisory_death_first_person",
)

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

    Never defaults: if any of the NINE columns rule v1 actually reads
    (``_RULE_INPUTS``) is missing, ``age_band`` and ``age_band_driver``
    are null -- only ``age_band_rule`` is always known, since it names
    the rule consulted, not its verdict.

    The precondition is deliberately "all nine, always" rather than
    "whichever subset the clause that fired happens to read": an
    ``adult`` verdict from the first matching clause would in fact be
    safe even with a later clause's input missing, since adult is the
    highest band and nothing could raise it further -- but a ``child``
    verdict needs every one of the nine checked to be trustworthy, and
    a null-condition that changes depending on which clause fired is
    far harder to audit than one single precondition. Checking all
    nine, always, satisfies the "never without having read its inputs"
    requirement with one rule instead of three.

    Only these nine are preconditions. The other eighteen advisory
    columns -- positive_messages, role_models, religious_content, and
    every modifier no clause in rule v1 reads (advisory_sex_depicted,
    advisory_violence_first_person, and so on) -- must NOT be checked
    here: the spec commits to "one failed batch nulls its own columns
    and no others," and with 153 questions spread across 8 calls, a
    batch holding only those eighteen unrelated columns is a real
    scenario, not an edge case worth over-guarding against.
    """
    if any(columns.get(field) is None for field in _RULE_INPUTS):
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
        "between 13 and 14. NEVER DEFAULTS: if any of the nine advisory "
        "columns rule v1 actually reads is missing, the band is null, in "
        "both directions -- a reassuring 'child' about an unread song is "
        "harmful, and a conservative 'adult' would hide most of the "
        "repertoire. positive_messages, role_models, religious_content, "
        "and every modifier no clause reads are not preconditions, so a "
        "batch failure elsewhere never nulls this column. Advisory: a "
        "teacher's judgment, not a rating."
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

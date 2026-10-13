"""Agreement between the classifier and the committed labels.

WHAT THESE FIGURES ARE WORTH: the songs, the labels and the question
wording all come from one author, so a high agreement demonstrates that
the plumbing works and that obvious readings land. It cannot demonstrate
that the hard cases are handled. These numbers are an UPPER BOUND, not
an accuracy estimate, and any report quoting them must say so.

Four disciplines keep what validity is available:

1. The corpus and labels were frozen in a commit before any question
   wording existed.
2. The thirteen held-out songs are run once, at the end. No question
   may be reworded after seeing that result.
3. Disagreements are logged with their songs and NOT adjudicated here;
   they go to a human to arbitrate.
4. Agreement is reported per column, never as one composite, because
   the axes will not be equally learnable and an average would hide it.

One more thing this file is NOT: a place for student information. The
sensitive axis's flags exist for per-student exclusion, and this harness
only ever reports song-to-label agreement -- nothing about any student
is read, stored or printed here.
"""

from __future__ import annotations

import functools
import json
import os
from dataclasses import dataclass, field
from typing import Any

from .features import base
from .features.lyrics.assemble import assemble_text
from .features.lyrics.questions import Answer, Kind, Question
from .features.lyrics.vocabulary import (
    ADVISORIES, ADVISORY_MODIFIERS, SENSITIVE, THEMES, TONES,
)
from .loaders import load

SPLITS = {"dev": "dev", "held-out": "held_out"}

#: A probability at or above this is read as "the model said yes", to be
#: comparable with a boolean label.
FIRES = 0.5

#: The label vocabulary's own spelling for a handful of theme children
#: differs from the column name the axis actually declared (themes.py /
#: vocabulary.py), even though both describe the same child concept.
#: Keyed by (family, the label's own suffix) -> the real child slug.
#:
#: WHY THIS EXISTS AT ALL: the corpus (``songs.py`` / ``labels.json``)
#: was frozen before any question wording existed -- deliberately, so
#: that validating against it means something (see the module
#: docstring). That means the corpus author and the vocabulary author
#: (``vocabulary.py``) each independently picked one word out of the
#: same compound child name in the spec -- "devotional & prayer"
#: becomes ``religion_devotional`` on one side and ``religion_prayer``
#: on the other; "eating & drinking" becomes ``activities_eating`` and
#: ``activities_feasting``. Neither side is wrong and there is nothing
#: to guess at: this is the frozen-corpus design working exactly as
#: intended, not a defect in either vocabulary, so every pair here is
#: an alias of one concept, never a judgment call about which concept
#: a label "really" meant.
_THEME_LABEL_ALIASES: dict[tuple[str, str], str] = {
    ("religion", "liturgical"): "liturgy",
    ("religion", "devotional"): "prayer",
    ("social", "class_labour"): "class",
    ("social", "war_conflict"): "war",
    ("mythology", "folk_tradition"): "folk",
    ("activities", "eating"): "feasting",
}

#: Frozen label keys with no column counterpart at all, after aliasing
#: -- not a different spelling of a known child, but a concept the
#: axis vocabulary never declared under any spelling. Populated the
#: first time `_theme_columns` sees one.
#:
#: MUST BE EMPTY for the frozen corpus (pinned by
#: ``test_every_frozen_theme_label_key_maps_onto_a_column``). This is
#: not a diagnostic a reader can shrug off: a label silently dropped
#: from the comparison still counts toward nothing in either
#: ``agreed`` or ``of``, which inflates how much of the vocabulary
#: looks validated. ``print_agreement`` reports a non-empty set
#: prominently rather than leaving it to this module constant, so a
#: label key added by a future release that nobody mapped fails loudly
#: instead of quietly vanishing from the denominator.
UNMAPPABLE_LABEL_KEYS: set[str] = set()


@dataclass
class ColumnAgreement:
    column: str
    agreed: int = 0
    of: int = 0
    disagreements: list[str] = field(default_factory=list)


def _labels(corpus_dir: str) -> dict:
    path = os.path.join(corpus_dir, "labels.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def slugs_for(corpus_dir: str, split: str) -> list[str]:
    if split not in SPLITS:
        raise ValueError(f"unknown split: {split!r}; use dev or held-out")
    return sorted(_labels(corpus_dir)["split"][SPLITS[split]])


@functools.lru_cache(maxsize=None)
def _text_to_slug(corpus_dir: str) -> dict[str, str]:
    """Every song's reassembled lyric text, keyed back to its slug.

    Built once per corpus directory (the corpus is frozen, so the
    mapping never changes within a run) by reading every ``.musicxml``
    file directly -- not just the ones in one split -- so the oracle
    works whichever split it is asked about.
    """
    mapping: dict[str, str] = {}
    for name in sorted(os.listdir(corpus_dir)):
        if not name.endswith(".musicxml"):
            continue
        slug = name[: -len(".musicxml")]
        piece = load(os.path.join(corpus_dir, name))
        assembled = assemble_text(piece.parts[0])
        if assembled is not None:
            mapping[assembled.text] = slug
    return mapping


def _slug_for_text(corpus_dir: str, state: str) -> str:
    """Which song's lyrics this classifier-bound text came from."""
    slug = _text_to_slug(corpus_dir).get(state)
    if slug is None:
        raise KeyError(
            f"no song under {corpus_dir!r} reassembles to this lyric text"
        )
    return slug


def _theme_columns(themes: dict[str, Any]) -> dict[str, Any]:
    """Flatten the ``themes`` label block onto ``theme_*`` columns.

    Absent keys mean false (the label convention), so every family and
    every child the vocabulary declares gets an explicit False default
    first; only then are the label's own True entries applied on top.
    A handful of label keys spell a child differently from the column
    the axis declared (``_THEME_LABEL_ALIASES``, each pair the same
    frozen-corpus-vs-vocabulary spelling split, never a different
    concept); anything that still doesn't match a real child after
    aliasing is recorded in ``UNMAPPABLE_LABEL_KEYS`` -- which must stay
    empty for the frozen corpus -- and left out of this song's
    comparison, which ``print_agreement`` then surfaces prominently
    rather than letting it pass unnoticed.
    """
    out: dict[str, Any] = {}
    for family, (_text, children) in THEMES.items():
        out[f"theme_{family}"] = bool(themes.get(family, False))
        for slug, _child_text in children:
            out[f"theme_{family}_{slug}"] = False

    for key, value in themes.items():
        if key in THEMES:
            continue  # family-level; already set above
        matched_family = None
        for family in THEMES:
            if key.startswith(f"{family}_"):
                matched_family = family
                break
        if matched_family is None:
            UNMAPPABLE_LABEL_KEYS.add(f"themes.{key}")
            continue
        remainder = key[len(matched_family) + 1:]
        slug = _THEME_LABEL_ALIASES.get((matched_family, remainder), remainder)
        valid_slugs = {child_slug for child_slug, _t in THEMES[matched_family][1]}
        if slug not in valid_slugs:
            UNMAPPABLE_LABEL_KEYS.add(f"themes.{key}")
            continue
        out[f"theme_{matched_family}_{slug}"] = bool(value)
    return out


def _tone_columns(tone: dict[str, Any]) -> dict[str, Any]:
    return {f"tone_{slug}": bool(tone.get(slug, False)) for slug, _text in TONES}


def _advisory_columns(advisories: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for slug, _text in ADVISORIES:
        out[f"advisory_{slug}"] = int(advisories.get(slug, 0))
        for modifier, _mtext in ADVISORY_MODIFIERS:
            key = f"{slug}_{modifier}"
            out[f"advisory_{key}"] = bool(advisories.get(key, False))
    return out


def _sensitive_columns(sensitive: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for slug, _text in SENSITIVE:
        out[f"sensitive_{slug}"] = bool(sensitive.get(slug, False))
        out[f"sensitive_{slug}_centrality"] = int(
            sensitive.get(f"{slug}_centrality", 0)
        )
        out[f"sensitive_{slug}_first_person"] = bool(
            sensitive.get(f"{slug}_first_person", False)
        )
    return out


def _perspective_columns(perspective: dict[str, Any]) -> dict[str, Any]:
    """The ``perspective`` label block, copied as-is.

    Unlike every other block, this one's keys were authored to be the
    exact column names the perspective axis declared (``narrator_gender``,
    ``love_interest_cast_by_pronouns``, ``gender_adaptation_cost``, ...),
    and it is written exhaustively for every song -- including explicit
    ``null`` for the love-interest columns when there is no relational
    focus. No aliasing and no defaulting is needed or correct here: a
    default would turn a deliberate null into a guess.
    """
    return dict(perspective)


def _expected_columns(record: dict[str, Any]) -> dict[str, Any]:
    """A song's label record, flattened onto the column names the axes
    (Tasks 4-8) actually declared."""
    out: dict[str, Any] = {}
    out.update(_theme_columns(record.get("themes", {})))
    out.update(_tone_columns(record.get("tone", {})))
    out.update(_advisory_columns(record.get("advisories", {})))
    out.update(_sensitive_columns(record.get("sensitive", {})))
    out.update(_perspective_columns(record.get("perspective", {})))
    return out


def _answer_for(question: Question, value: Any) -> Answer:
    """The oracle's answer for one question, given the expected label
    value for its column.

    ``value`` can be ``None`` (a gated-closed perspective column, or a
    question with no corresponding expected entry at all); in that case
    the oracle still has to return something that validates against the
    question's declared kind, but what it returns doesn't matter for
    agreement -- the axis that owns a null column nulls it unconditionally
    regardless of what was asked, which is exactly what makes the
    gating correct rather than this oracle.
    """
    if question.kind is Kind.NOUL:
        probability = 1.0 if value is True else 0.0
        return Answer(question.id, probability=probability)
    if question.kind is Kind.CHOICE:
        if isinstance(value, str) and value in question.options:
            return Answer(question.id, choice=value)
        fallback = "unspecified" if "unspecified" in question.options else question.options[0]
        return Answer(question.id, choice=fallback)
    if question.kind is Kind.SCORE:
        score = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0
        return Answer(question.id, score=score)
    raise ValueError(f"unknown question kind: {question.kind!r}")


def _agrees(computed: Any, expected: Any) -> bool:
    """Compare one column's computed value against its expected label.

    ``None`` on either side, unless both sides are ``None``, is always a
    disagreement: an unasked column is not the same claim as a label of
    zero or false, so it must never be scored as if it agreed with one.
    A probability is compared to a boolean label via ``FIRES``; a score
    or a derived integer is compared to an integer label exactly; a
    choice is compared to a string label exactly.
    """
    if computed is None and expected is None:
        return True
    if computed is None or expected is None:
        return False
    if isinstance(expected, bool):
        return (computed >= FIRES) == expected
    if isinstance(expected, int):
        return computed == expected
    if isinstance(expected, str):
        return computed == expected
    raise TypeError(f"no comparison rule for expected value {expected!r}")


def oracle_client(corpus_dir: str, split: str):
    """A client that answers from the labels: the harness's own control.

    Without it, a harness that compared the wrong way round, or
    compared nothing at all, would look identical to a model that
    disagreed with every label.
    """
    labels = _labels(corpus_dir)["labels"]

    class _Oracle:
        model = "oracle/labels"
        calls_made = 0

        def ask(self, state, questions):
            slug = _slug_for_text(corpus_dir, state)
            expected = _expected_columns(labels[slug])
            answers = []
            for question in questions:
                value = expected.get(question.column)
                answers.append(_answer_for(question, value))
            self.calls_made += 1
            return answers

    return _Oracle()


def compare_corpus(corpus_dir: str, split: str) -> list[ColumnAgreement]:
    """Per-column agreement over one split. Never a composite."""
    labels = _labels(corpus_dir)["labels"]
    results: dict[str, ColumnAgreement] = {}

    for slug in slugs_for(corpus_dir, split):
        piece = load(os.path.join(corpus_dir, f"{slug}.musicxml"))
        computed = base.extract_part(piece.parts[0], piece, groups_filter=["lyrics"])
        for column, expected in _expected_columns(labels[slug]).items():
            result = results.setdefault(column, ColumnAgreement(column))
            result.of += 1
            if _agrees(computed.get(column), expected):
                result.agreed += 1
            else:
                result.disagreements.append(slug)

    return [results[column] for column in sorted(results)]


def print_agreement(corpus_dir: str, split: str) -> None:
    print(f"split: {split}")
    print("These figures are an upper bound, not an accuracy estimate: the "
          "songs, labels and question wording share one author.")
    if split == "held-out" and "cast-agreement" in slugs_for(corpus_dir, split):
        print("NOTE: cast-agreement is Italian, the only non-English song; "
              "its figures are not validation of the (English-only) spec "
              "and must be read with that caveat.")

    results = compare_corpus(corpus_dir, split)

    if UNMAPPABLE_LABEL_KEYS:
        # Loud and first, not a footnote: a label key excluded from
        # every comparison below inflates how much of the vocabulary
        # the table appears to validate.
        print()
        print(
            "WARNING: these frozen label keys have no column counterpart "
            "and were excluded from EVERY comparison below -- the "
            "coverage below is an overcount of what was actually "
            "validated:"
        )
        for key in sorted(UNMAPPABLE_LABEL_KEYS):
            print(f"  {key}")
        print()

    for result in results:
        print(f"{result.column:<44} {result.agreed:>4}/{result.of:<4}")
    print()
    print("disagreements, for a human to arbitrate:")
    for result in results:
        for slug in result.disagreements:
            print(f"  {result.column:<44} {slug}")

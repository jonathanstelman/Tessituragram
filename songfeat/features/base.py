"""Feature registry.

Each extractor declares the fields it produces, so the output schema can be
reported without running anything -- useful for building CSV headers, and
for documenting what the pipeline measures.

Extractors are scoped to either a part (one row per instrumental/vocal line)
or the whole piece (ensemble-level facts like tempo and key, which have no
meaningful per-part variant). ``extract_part`` and ``extract_piece`` run only
the extractors registered at the matching scope.

Which note set a feature measures
---------------------------------

"The line" means two different things across the feature modules, and the
choice is deliberate in each case. There is no single right answer, so the
rule is stated here once rather than inferred per module:

* ``part.notes`` -- every note, chord members included. Used by
  ``tessitura``, ``vocal_load``, ``pitch_range``, ``basic.text`` and
  ``passaggi``. These are *inventory* measurements: how much pitch, how
  much phonation, how much time in a zone. A chord's third voice is real
  sound, so dropping it would under-report the demand on whoever sings it.

* ``PartContext.monophonic`` -- the highest note at each onset. Used by
  ``leaps``, ``chromaticism``, ``text_setting``, ``runs`` and
  ``phrasing``. These are *melodic* measurements, defined over a sequence
  of successive notes. An interval, a melisma or a run between two
  simultaneous notes is not a thing, so the line has to be reduced to one
  note per onset before they mean anything.

On a monophonic part -- which the whole aria corpus is -- the two sets are
identical and nothing distinguishes them. On a chordal or divisi part they
differ, and two columns that read like the same measurement can disagree:
``basic.n_lyric_syllables`` counts lyrics over every note while
``text_setting.n_syllables`` counts them over the monophonic reduction, so
a syllable attached to a lower chord member is counted by the first and
not the second. Both feature descriptions say so.

A note-set choice is a measurement decision. Changing one changes what a
published column means, so it belongs in a review, not in a refactor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from ..model import Part, Piece

PartExtractor = Callable[[Part, Piece], dict[str, Any]]


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    group: str
    scope: str            # "part" or "piece"
    source: str           # "songfeat" | "jsymbolic" | "music21-native"
    description: str
    fields: tuple[str, ...]
    func: Callable
    dtype: str = "float"
    citation: str | None = None
    #: Formats where this feature is fully meaningful. MIDI carries no pitch
    #: spelling, so chromaticism features are inferred there and stronger from
    #: MusicXML. None means "equally valid for every supported format".
    best_with: tuple[str, ...] | None = None
    #: True for a feature that runs only when its group is named. Every
    #: group registered at the start of this project was deterministic,
    #: offline and free, so "all registered features" and "everything a
    #: default run should do" were the same set. The ``lyrics`` group is
    #: none of those three -- it calls a paid network service -- so it
    #: runs only when asked for, and an unfiltered ``schema()`` or
    #: ``extract_part()`` leaves it out rather than emitting 178 columns
    #: that can only ever be null. Naming the group explicitly
    #: (``--groups lyrics``) is the only way in.
    opt_in: bool = False


_REGISTRY: dict[str, FeatureSpec] = {}


def feature(name, group, scope, source, description, fields,
            dtype="float", citation=None, best_with=None, opt_in=False):
    """Register an extractor under ``name``, scoped to a part or a piece."""
    if scope not in ("part", "piece"):
        raise ValueError(f"scope must be 'part' or 'piece', got {scope!r}")

    def decorator(func):
        if name in _REGISTRY:
            raise ValueError(f"duplicate feature name: {name}")
        _REGISTRY[name] = FeatureSpec(
            name=name, group=group, scope=scope, source=source,
            description=description, fields=tuple(fields), func=func,
            dtype=dtype, citation=citation, best_with=best_with,
            opt_in=opt_in,
        )
        return func

    return decorator


def registry() -> dict[str, FeatureSpec]:
    return dict(_REGISTRY)


def groups() -> list[str]:
    return sorted({spec.group for spec in _REGISTRY.values()})


def opt_in_groups() -> list[str]:
    """Groups that no unfiltered call includes. See ``FeatureSpec.opt_in``."""
    return sorted({spec.group for spec in _REGISTRY.values() if spec.opt_in})


def _selected(specs: Iterable[FeatureSpec],
              groups_filter: Iterable[str] | None) -> list[FeatureSpec]:
    """The specs a filter asks for.

    No filter means "every group that is not opt-in" -- not "every
    registered group". An opt-in group has to be named, so that a
    default run stays exactly what it was before the group existed.
    """
    wanted = set(groups_filter) if groups_filter else None
    if wanted is None:
        return [spec for spec in specs if not spec.opt_in]
    return [spec for spec in specs if spec.group in wanted]


def schema(groups_filter: Iterable[str] | None = None) -> list[str]:
    """Ordered output field names, without parsing anything.

    Identity columns (source path, part index, ...) come first, matching
    the order ``FeatureRecord.flat()`` emits them in.

    An opt-in group's columns appear only when the group is named: see
    ``_selected``.
    """
    from ..record import FeatureRecord  # local import avoids a cycle

    names = list(FeatureRecord.IDENTITY)
    for spec in _selected(_REGISTRY.values(), groups_filter):
        names.extend(spec.fields)
    return names


def _run(specs, *args) -> dict[str, Any]:
    """Run ``specs`` against ``args`` and merge their output.

    A failing extractor yields None for its fields rather than aborting the
    whole record, so one bad feature cannot lose an entire batch run. Errors
    are collected under a single ``_errors`` key rather than one per feature,
    so callers can relocate them without guessing field names.

    A feature may also report a *partial* failure -- it produced its
    columns, but something it asked for came back as an error -- by
    returning its own ``_errors`` mapping alongside its columns. Those
    entries are merged into this dict rather than overwriting it, so a
    reason belonging to one axis's columns (a classifier question that
    answered "HTTP 503") reaches the record instead of being dropped,
    leaving a bare ``None`` with nothing anywhere to explain it.
    """
    out: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for spec in specs:
        try:
            produced = dict(spec.func(*args))
            errors.update(produced.pop("_errors", None) or {})
            out.update(produced)
        except Exception as exc:  # noqa: BLE001 - deliberate per-feature isolation
            out.update(dict.fromkeys(spec.fields))
            errors[spec.name] = f"{type(exc).__name__}: {exc}"
    out["_errors"] = errors
    return out


def extract_part(part, piece, groups_filter=None) -> dict[str, Any]:
    specs = [
        s for s in _selected(_REGISTRY.values(), groups_filter)
        if s.scope == "part"
    ]
    return _run(specs, part, piece)


def extract_piece(piece, groups_filter=None) -> dict[str, Any]:
    specs = [
        s for s in _selected(_REGISTRY.values(), groups_filter)
        if s.scope == "piece"
    ]
    return _run(specs, piece)

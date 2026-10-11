"""Feature registry.

Each extractor declares the fields it produces, so the output schema can be
reported without running anything -- useful for building CSV headers, and
for documenting what the pipeline measures.

Extractors are scoped to either a part (one row per instrumental/vocal line)
or the whole piece (ensemble-level facts like tempo and key, which have no
meaningful per-part variant). ``extract_part`` and ``extract_piece`` run only
the extractors registered at the matching scope.
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


_REGISTRY: dict[str, FeatureSpec] = {}


def feature(name, group, scope, source, description, fields,
            dtype="float", citation=None, best_with=None):
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
        )
        return func

    return decorator


def registry() -> dict[str, FeatureSpec]:
    return dict(_REGISTRY)


def groups() -> list[str]:
    return sorted({spec.group for spec in _REGISTRY.values()})


def schema(groups_filter: Iterable[str] | None = None) -> list[str]:
    """Ordered output field names, without parsing anything.

    Identity columns (source path, part index, ...) come first, matching
    the order ``FeatureRecord.flat()`` emits them in.
    """
    from ..record import FeatureRecord  # local import avoids a cycle

    names = list(FeatureRecord.IDENTITY)
    wanted = set(groups_filter) if groups_filter else None
    for spec in _REGISTRY.values():
        if wanted is None or spec.group in wanted:
            names.extend(spec.fields)
    return names


def _run(specs, *args) -> dict[str, Any]:
    """Run ``specs`` against ``args`` and merge their output.

    A failing extractor yields None for its fields rather than aborting the
    whole record, so one bad feature cannot lose an entire batch run. Errors
    are collected under a single ``_errors`` key rather than one per feature,
    so callers can relocate them without guessing field names.
    """
    out: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for spec in specs:
        try:
            out.update(spec.func(*args))
        except Exception as exc:  # noqa: BLE001 — deliberate per-feature isolation
            out.update(dict.fromkeys(spec.fields))
            errors[spec.name] = f"{type(exc).__name__}: {exc}"
    out["_errors"] = errors
    return out


def extract_part(part, piece, groups_filter=None) -> dict[str, Any]:
    wanted = set(groups_filter) if groups_filter else None
    specs = [
        s for s in _REGISTRY.values()
        if s.scope == "part" and (wanted is None or s.group in wanted)
    ]
    return _run(specs, part, piece)


def extract_piece(piece, groups_filter=None) -> dict[str, Any]:
    wanted = set(groups_filter) if groups_filter else None
    specs = [
        s for s in _REGISTRY.values()
        if s.scope == "piece" and (wanted is None or s.group in wanted)
    ]
    return _run(specs, piece)

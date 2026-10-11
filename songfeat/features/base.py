"""Feature registry.

Each extractor declares the fields it produces, so the output schema can be
reported without running anything -- useful for building CSV headers, and
for documenting what the pipeline measures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from ..model import Piece

Extractor = Callable[[Piece], dict[str, Any]]


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    group: str
    description: str
    fields: tuple[str, ...]
    func: Extractor


_REGISTRY: dict[str, FeatureSpec] = {}


def feature(name: str, group: str, description: str, fields: Iterable[str]):
    """Register an extractor under ``name``."""

    def decorator(func: Extractor) -> Extractor:
        if name in _REGISTRY:
            raise ValueError(f"duplicate feature name: {name}")
        _REGISTRY[name] = FeatureSpec(
            name=name,
            group=group,
            description=description,
            fields=tuple(fields),
            func=func,
        )
        return func

    return decorator


def registry() -> dict[str, FeatureSpec]:
    return dict(_REGISTRY)


def groups() -> list[str]:
    return sorted({spec.group for spec in _REGISTRY.values()})


def schema(groups_filter: Iterable[str] | None = None) -> list[str]:
    """Ordered output field names, without parsing anything."""
    wanted = set(groups_filter) if groups_filter else None
    names: list[str] = []
    for spec in _REGISTRY.values():
        if wanted is None or spec.group in wanted:
            names.extend(spec.fields)
    return names


def extract(piece: Piece, groups_filter: Iterable[str] | None = None) -> dict[str, Any]:
    """Run every registered extractor and merge the results.

    A failing extractor yields None for its fields rather than aborting the
    whole record, so one bad feature cannot lose an entire batch run.
    """
    wanted = set(groups_filter) if groups_filter else None
    out: dict[str, Any] = {}
    for spec in _REGISTRY.values():
        if wanted is not None and spec.group not in wanted:
            continue
        try:
            values = spec.func(piece)
        except Exception as exc:  # noqa: BLE001 - deliberate per-feature isolation
            values = {field: None for field in spec.fields}
            values[f"_error_{spec.name}"] = f"{type(exc).__name__}: {exc}"
        out.update(values)
    return out

"""The typed boundary object. Extraction produces these; sinks consume them."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

FeatureValue = float | int | str | bool | None


class FeatureRecord(BaseModel):
    """One analysed part."""

    source_path: str
    source_format: str
    part_index: int
    part_name: str | None = None
    is_vocal_candidate: bool = False
    vocal_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    features: dict[str, FeatureValue] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)

    #: Identity columns, in the order tabular sinks emit them.
    IDENTITY: ClassVar[tuple[str, ...]] = (
        "source_path", "source_format", "part_index", "part_name",
        "is_vocal_candidate", "vocal_confidence",
    )

    def flat(self) -> dict[str, Any]:
        """Identity fields merged with features, for tabular sinks."""
        row: dict[str, Any] = {name: getattr(self, name) for name in self.IDENTITY}
        row.update(self.features)
        for name, message in self.errors.items():
            row[f"_error_{name}"] = message
        return row

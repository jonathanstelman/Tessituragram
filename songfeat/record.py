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

    #: The four signals behind ``vocal_confidence``, each in 0..1
    #: (songfeat/vocal.py:WEIGHTS gives their weights). Carried as four
    #: scalar columns rather than one JSON blob because the point of
    #: surfacing them is that a user can sort, filter and plot them in the
    #: CSV or sheet they already have open -- "show me every part where
    #: range and monophony are high but naming is 0" is a column
    #: comparison, and a JSON string in one cell would have to be parsed
    #: before it answered anything. They are identity, not features:
    #: ``detect_vocal`` produces them, no registered extractor does, and
    #: they explain a column (``vocal_confidence``) that is already here.
    #:
    #: Without them a wrong guess is unauditable in exactly the case that
    #: matters. On lyric-less input the lyrics signal is always 0.0 at
    #: weight 0.45, so confidence cannot exceed 0.55 while a monophonic
    #: in-range part already reaches 0.45: the 0.5 threshold sits inside
    #: the 0.10 naming contributes, and a genuine vocal part reading
    #: "0.45 / False" gives the user nothing to go on.
    vocal_signal_lyrics: float | None = None
    vocal_signal_monophony: float | None = None
    vocal_signal_range: float | None = None
    vocal_signal_naming: float | None = None

    features: dict[str, FeatureValue] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)

    #: Identity columns, in the order tabular sinks emit them.
    IDENTITY: ClassVar[tuple[str, ...]] = (
        "source_path", "source_format", "part_index", "part_name",
        "is_vocal_candidate", "vocal_confidence",
        "vocal_signal_lyrics", "vocal_signal_monophony",
        "vocal_signal_range", "vocal_signal_naming",
    )

    def flat(self) -> dict[str, Any]:
        """Identity fields merged with features, for tabular sinks."""
        row: dict[str, Any] = {name: getattr(self, name) for name in self.IDENTITY}
        row.update(self.features)
        for name, message in self.errors.items():
            row[f"_error_{name}"] = message
        return row

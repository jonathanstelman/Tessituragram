from __future__ import annotations

import csv
import json
from typing import Sequence

from ..record import FeatureRecord
from .base import BaseSink


def _flatten(record) -> dict:
    """A record's columns as a flat ``{name: value}`` mapping.

    Accepts a ``FeatureRecord`` (via its own ``flat()``) or an already-flat
    mapping, since a caller writing a derived/aggregated row -- one with no
    identity fields to flatten -- can hand either sink a plain dict.
    """
    return record.flat() if hasattr(record, "flat") else dict(record)


class CsvSink(BaseSink):
    """Wide rows via flat(). Buffers, because error columns are only known
    once every record has been seen."""

    def __init__(self, path: str, exclude: Sequence[str] = ()) -> None:
        self.path = path
        self._exclude = frozenset(exclude)
        self._rows: list[dict] = []

    def open(self, schema: list[str]) -> None:
        super().open([name for name in schema if name not in self._exclude])

    def write(self, record) -> None:
        row = _flatten(record)
        self._rows.append({k: v for k, v in row.items() if k not in self._exclude})

    def close(self) -> None:
        extra = sorted({k for row in self._rows for k in row if k not in self.schema})
        with open(self.path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=self.schema + extra, extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(self._rows)


class JsonlSink(BaseSink):
    """One record per line. Streams; the default for large batches."""

    def __init__(self, path: str, exclude: Sequence[str] = ()) -> None:
        self.path = path
        self._exclude = frozenset(exclude)
        self._handle = None

    def open(self, schema: list[str]) -> None:
        super().open([name for name in schema if name not in self._exclude])
        self._handle = open(self.path, "w", encoding="utf-8")

    def write(self, record: FeatureRecord) -> None:
        # Excluded columns live wherever the model puts them -- most are
        # nested under "features", not top-level -- so both are checked
        # rather than assuming either shape.
        payload = record.model_dump()
        for name in self._exclude:
            payload.pop(name, None)
            payload.get("features", {}).pop(name, None)
        self._handle.write(json.dumps(payload) + "\n")

    def close(self) -> None:
        if self._handle:
            self._handle.close()
            self._handle = None


class JsonSink(BaseSink):
    """A single array. Convenient for small runs; holds everything in memory."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._records: list[FeatureRecord] = []

    def write(self, record: FeatureRecord) -> None:
        self._records.append(record)

    def close(self) -> None:
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump([r.model_dump() for r in self._records], handle, indent=2)

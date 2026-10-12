from __future__ import annotations

import csv
import json

from ..record import FeatureRecord
from .base import BaseSink


class CsvSink(BaseSink):
    """Wide rows via flat(). Buffers, because error columns are only known
    once every record has been seen."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._rows: list[dict] = []

    def write(self, record: FeatureRecord) -> None:
        self._rows.append(record.flat())

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

    def __init__(self, path: str) -> None:
        self.path = path
        self._handle = None

    def open(self, schema: list[str]) -> None:
        super().open(schema)
        self._handle = open(self.path, "w", encoding="utf-8")

    def write(self, record: FeatureRecord) -> None:
        self._handle.write(record.model_dump_json() + "\n")

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

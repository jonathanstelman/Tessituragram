"""Sinks receive records. Extraction never serialises."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..record import FeatureRecord


@runtime_checkable
class Sink(Protocol):
    def open(self, schema: list[str]) -> None: ...
    def write(self, record: FeatureRecord) -> None: ...
    def close(self) -> None: ...


class BaseSink:
    """Context-manager plumbing shared by the concrete sinks."""

    def open(self, schema: list[str]) -> None:
        self.schema = list(schema)

    def write(self, record: FeatureRecord) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


class MemorySink(BaseSink):
    """Collects records in a list. For tests and small in-process runs."""

    def __init__(self) -> None:
        self.records: list[FeatureRecord] = []

    def write(self, record: FeatureRecord) -> None:
        self.records.append(record)

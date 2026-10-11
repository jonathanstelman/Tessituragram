import pytest

from songfeat.record import FeatureRecord
from songfeat.sinks.sheets import SheetsSink

SCHEMA = ["source_path", "part_index", "min_midi"]


class FakeWorksheet:
    def __init__(self, existing=None):
        self.rows = list(existing or [])
        self.append_calls = 0

    def get_all_values(self):
        return self.rows

    def append_rows(self, rows, **kwargs):
        self.append_calls += 1
        self.rows.extend(rows)


class FakeClient:
    """Mimics the two gspread calls SheetsSink makes."""

    def __init__(self, sheet):
        self._sheet = sheet

    def open_by_key(self, key):
        return self

    def worksheet(self, title):
        return self._sheet


def record(index: int) -> FeatureRecord:
    return FeatureRecord(
        source_path="song.mid", source_format="midi", part_index=index,
        features={"min_midi": 60 + index},
    )


def sink_with(worksheet, **kwargs) -> SheetsSink:
    return SheetsSink("sheet-id", client=FakeClient(worksheet), **kwargs)


def test_header_is_written_to_an_empty_sheet():
    worksheet = FakeWorksheet()
    with sink_with(worksheet) as sink:
        sink.open(SCHEMA)
        sink.write(record(0))
    assert worksheet.rows[0] == SCHEMA


def test_header_is_not_rewritten_to_a_populated_sheet():
    worksheet = FakeWorksheet([SCHEMA])
    with sink_with(worksheet) as sink:
        sink.open(SCHEMA)
        sink.write(record(0))
    assert worksheet.rows.count(SCHEMA) == 1


def test_rows_are_appended_in_batches_not_one_call_each():
    worksheet = FakeWorksheet()
    with sink_with(worksheet, batch_size=3) as sink:
        sink.open(SCHEMA)
        for i in range(6):
            sink.write(record(i))
    # Exactly: the header write, plus two batches of three mid-stream.
    # A looser bound (e.g. <=) would also pass an implementation that
    # ignores batch_size and dumps everything in one flush at close().
    assert worksheet.append_calls == 3


def test_remaining_rows_are_flushed_on_close():
    worksheet = FakeWorksheet()
    with sink_with(worksheet, batch_size=100) as sink:
        sink.open(SCHEMA)
        sink.write(record(0))
    assert len(worksheet.rows) == 2       # header + one row


def test_values_are_ordered_to_match_the_schema():
    worksheet = FakeWorksheet()
    with sink_with(worksheet) as sink:
        sink.open(SCHEMA)
        sink.write(record(5))
    assert worksheet.rows[1] == ["song.mid", 5, 65]


def test_missing_feature_becomes_an_empty_cell():
    worksheet = FakeWorksheet()
    with sink_with(worksheet) as sink:
        sink.open(SCHEMA + ["not_computed"])
        sink.write(record(0))
    assert worksheet.rows[1][-1] == ""


def test_mismatched_header_raises_instead_of_appending_misaligned_rows():
    worksheet = FakeWorksheet([["source_path", "part_index", "max_midi"]])
    with sink_with(worksheet) as sink:
        with pytest.raises(ValueError):
            sink.open(SCHEMA)
    assert worksheet.rows == [["source_path", "part_index", "max_midi"]]


def test_importing_the_sheets_module_does_not_require_the_google_client():
    """Proves the import is lazy, not merely that `import songfeat` works.

    `import songfeat` never touches `songfeat.sinks` at all (see
    songfeat/__init__.py), so asserting on it would pass even for a
    sheets.py with `import gspread` at module top level. Importing
    songfeat.sinks.sheets directly, with gspread blocked, is the only way
    to tell a lazy import (this must succeed) from an eager one (this
    would raise before SheetsSink is ever touched).
    """
    import subprocess
    import sys
    code = """
import sys
sys.modules['gspread'] = None
import songfeat.sinks.sheets
print('import-ok')
try:
    songfeat.sinks.sheets.SheetsSink('sheet-id')
except ImportError:
    print('construct-failed')
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert "import-ok" in result.stdout, result.stderr
    assert "construct-failed" in result.stdout, result.stderr

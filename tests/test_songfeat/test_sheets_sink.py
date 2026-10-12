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
    # Exactly: the header write, plus two batches of three. Rows are now
    # buffered and flushed at close(), because the error columns are only
    # known then, but they are still chunked by batch_size -- the Sheets
    # quota is per API call, so one 6-row call would be the regression
    # this guards. A looser bound (e.g. <=) would pass an implementation
    # that ignores batch_size and dumps everything in a single call.
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


# --- Fix round 3: error columns, and the re-run hazard --------------------

def failing_record(index: int) -> FeatureRecord:
    return FeatureRecord(
        source_path="song.mid", source_format="midi", part_index=index,
        features={"min_midi": 60 + index},
        errors={"js_polyrhythms": "TypeError: no pulses"},
    )


def test_error_columns_reach_the_sheet():
    """`schema()` has no error columns -- they are only known once every
    record has been seen -- so a header written at open() and rows taken
    `row.get(column, "")` over it discarded every reason. CsvSink buffers
    for exactly this reason; this now does too."""
    worksheet = FakeWorksheet()
    with sink_with(worksheet) as sink:
        sink.open(SCHEMA)
        sink.write(failing_record(0))
    assert worksheet.rows[0] == SCHEMA + ["_error_js_polyrhythms"]
    assert worksheet.rows[1][-1] == "TypeError: no pulses"


def test_error_columns_are_shared_across_rows():
    """One record failing an extractor widens the sheet for all of them,
    and a row that did not fail gets a blank, not a missing cell."""
    worksheet = FakeWorksheet()
    with sink_with(worksheet) as sink:
        sink.open(SCHEMA)
        sink.write(record(0))
        sink.write(failing_record(1))
    assert worksheet.rows[0] == SCHEMA + ["_error_js_polyrhythms"]
    assert worksheet.rows[1] == ["song.mid", 0, 60, ""]
    assert worksheet.rows[2] == ["song.mid", 1, 61, "TypeError: no pulses"]


def test_a_sheet_without_an_error_column_refuses_to_swallow_the_reason():
    """Appending under a header that has no room for the reason is the
    defect being fixed, so widening an existing sheet is refused loudly
    rather than silently dropping the message."""
    worksheet = FakeWorksheet([SCHEMA])
    with sink_with(worksheet) as sink:
        sink.open(SCHEMA)
        sink.write(failing_record(0))
        with pytest.raises(ValueError, match="_error_js_polyrhythms"):
            sink.close()


def test_an_existing_error_column_is_reused():
    header = SCHEMA + ["_error_js_polyrhythms"]
    worksheet = FakeWorksheet([header])
    with sink_with(worksheet) as sink:
        sink.open(SCHEMA)
        sink.write(failing_record(0))
    assert worksheet.rows.count(header) == 1
    assert worksheet.rows[1] == ["song.mid", 0, 60, "TypeError: no pulses"]


def test_the_docstring_warns_that_a_re_run_duplicates_rows():
    """The spec's optional key column (source_path + part_index) was never
    implemented, and the ruling is to document the omission rather than
    deduplicate. An invisible duplication hazard is the defect; this test
    keeps the warning from being dropped."""
    text = SheetsSink.__doc__
    assert "duplicat" in text.lower(), text
    assert "source_path" in text and "part_index" in text, text


def test_a_re_run_really_does_append_a_second_time():
    """Proves the documented hazard is real, so the docstring is not
    describing something that cannot happen."""
    worksheet = FakeWorksheet()
    for _ in range(2):
        with sink_with(worksheet) as sink:
            sink.open(SCHEMA)
            sink.write(record(0))
    assert worksheet.rows == [SCHEMA, ["song.mid", 0, 60], ["song.mid", 0, 60]]

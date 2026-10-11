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
    # Two batches of three, plus the header write.
    assert worksheet.append_calls <= 3


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


def test_importing_songfeat_does_not_require_the_google_client():
    """The optional dependency must not leak into the package import."""
    import subprocess
    import sys
    code = (
        "import sys; "
        "sys.modules['gspread'] = None; "
        "import songfeat; print('ok')"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert "ok" in result.stdout

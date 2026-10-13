import csv
import json

from songfeat.record import FeatureRecord
from songfeat.sinks.base import MemorySink
from songfeat.sinks.files import CsvSink, JsonSink, JsonlSink

SCHEMA = ["source_path", "source_format", "part_index", "part_name",
          "is_vocal_candidate", "vocal_confidence", "min_midi"]


def record(index: int = 0, **extra) -> FeatureRecord:
    return FeatureRecord(
        source_path="song.mid", source_format="midi", part_index=index,
        part_name="Voice", features={"min_midi": 60 + index}, **extra
    )


def test_memory_sink_collects_records():
    with MemorySink() as sink:
        sink.open(SCHEMA)
        sink.write(record())
    assert len(sink.records) == 1


def test_csv_sink_writes_header_and_rows(tmp_path):
    path = tmp_path / "out.csv"
    with CsvSink(str(path)) as sink:
        sink.open(SCHEMA)
        sink.write(record(0))
        sink.write(record(1))
    with path.open() as f:
        rows = list(csv.DictReader(f))
    assert [r["min_midi"] for r in rows] == ["60", "61"]
    assert list(rows[0])[:2] == ["source_path", "source_format"]


def test_csv_sink_includes_error_columns_not_in_schema(tmp_path):
    path = tmp_path / "out.csv"
    with CsvSink(str(path)) as sink:
        sink.open(SCHEMA)
        sink.write(record(0, errors={"tessitura": "boom"}))
    assert "_error_tessitura" in path.read_text().splitlines()[0]


def test_jsonl_sink_writes_one_object_per_line(tmp_path):
    path = tmp_path / "out.jsonl"
    with JsonlSink(str(path)) as sink:
        sink.open(SCHEMA)
        sink.write(record(0))
        sink.write(record(1))
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["part_index"] == 1


def test_jsonl_keeps_errors_nested(tmp_path):
    path = tmp_path / "out.jsonl"
    with JsonlSink(str(path)) as sink:
        sink.open(SCHEMA)
        sink.write(record(0, errors={"tessitura": "boom"}))
    payload = json.loads(path.read_text())
    assert payload["errors"]["tessitura"] == "boom"


def test_json_sink_writes_a_single_array(tmp_path):
    path = tmp_path / "out.json"
    with JsonSink(str(path)) as sink:
        sink.open(SCHEMA)
        sink.write(record(0))
        sink.write(record(1))
    payload = json.loads(path.read_text())
    assert isinstance(payload, list) and len(payload) == 2


def test_a_csv_sink_may_decline_to_write_the_provenance_columns(tmp_path):
    """Provenance is mandatory on the RECORD; a sink may omit it. That way
    it can be left out of a teacher's spreadsheet deliberately, but never
    lost by accident."""
    path = tmp_path / "o.csv"
    sink = CsvSink(str(path), exclude=("clf_model", "clf_question_set"))
    sink.open(["title", "clf_model", "clf_question_set", "theme_love"])
    sink.write({"title": "A", "clf_model": "fake/jev-1",
                "clf_question_set": "full@v1", "theme_love": 0.9})
    sink.close()

    header, row = path.read_text(encoding="utf-8").splitlines()[:2]
    assert header.split(",") == ["title", "theme_love"]
    assert "fake/jev-1" not in row


def test_a_jsonl_sink_may_decline_to_write_the_provenance_columns(tmp_path):
    """The same exclusion, for the sink whose columns live nested under
    ``features`` rather than flattened -- the excluded name must be
    stripped from both places it could appear."""
    path = tmp_path / "o.jsonl"
    with JsonlSink(str(path), exclude=("clf_model",)) as sink:
        sink.open(["source_path", "source_format", "part_index"])
        sink.write(FeatureRecord(
            source_path="song.mid", source_format="midi", part_index=0,
            features={"clf_model": "fake/jev-1", "theme_love": 0.9},
        ))
    payload = json.loads(path.read_text().strip())
    assert "clf_model" not in payload["features"]
    assert payload["features"]["theme_love"] == 0.9


def test_sinks_are_safe_to_close_with_nothing_written(tmp_path):
    """Closing without a write produces a valid empty artifact, not nothing.

    Asserts the artifacts rather than only that no exception escaped: a sink
    that silently wrote no file at all would also "not raise".
    """
    csv_path = tmp_path / "a.csv"
    json_path = tmp_path / "b.json"
    jsonl_path = tmp_path / "c.jsonl"

    for sink, path in ((CsvSink(str(csv_path)), csv_path),
                       (JsonSink(str(json_path)), json_path),
                       (JsonlSink(str(jsonl_path)), jsonl_path)):
        with sink:
            sink.open(SCHEMA)
        assert path.exists(), path

    # CSV keeps its header so the columns are still documented; the other two
    # have no header concept, so they are an empty array and an empty file.
    assert csv_path.read_text().splitlines() == [",".join(SCHEMA)]
    assert json.loads(json_path.read_text()) == []
    assert jsonl_path.read_text() == ""

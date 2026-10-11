import os

from songfeat.pipeline import analyze_file, run
from songfeat.sinks.base import MemorySink

ARIA = os.path.join("data", "test_data_arias", "1-I.mid")


def test_one_record_per_part():
    records = list(analyze_file(ARIA))
    assert len(records) == 1
    assert records[0].part_index == 0


def test_record_carries_identity_and_features():
    record = next(iter(analyze_file(ARIA, drop_trailing_marker=True)))
    assert record.source_format == "midi"
    assert record.features["min_note"] == "D2"
    assert record.features["max_note"] == "E4"


def test_piece_scoped_features_are_denormalised_onto_the_record():
    record = next(iter(analyze_file(ARIA)))
    assert record.features["tempo_initial_bpm"] == 140.0


def test_multipart_file_yields_one_record_per_part(tmp_path):
    from music21 import corpus, converter
    out = tmp_path / "chorale.musicxml"
    converter.parse(corpus.getWork("bach/bwv66.6")).write("musicxml", fp=str(out))
    records = list(analyze_file(str(out)))
    assert len(records) == 4
    assert [r.part_index for r in records] == [0, 1, 2, 3]
    # Pitch ranges differ per part; pooling would make them identical.
    assert len({r.features["min_midi"] for r in records}) > 1


def test_run_reports_failures_without_losing_good_records(tmp_path):
    bad = tmp_path / "broken.mid"
    bad.write_bytes(b"nope")
    sink = MemorySink()
    count, failures = run([str(bad), ARIA], sink)
    assert count == 1
    assert len(failures) == 1
    assert "broken.mid" in failures[0][0]


def test_run_through_a_real_sink_produces_a_correct_record():
    """End-to-end on real corpus data, not a hand-built stub (see Task 6 postmortem).

    Independently verified against the MIDI file with music21 directly
    (not via songfeat): the file's only tempo mark is 140bpm at offset 0,
    and its last note is a C1 at offset 476.0 -- the trailing reference
    marker that ``drop_trailing_marker`` strips. Excluding it, the sorted
    MIDI numbers in the file run from 38 (D2) to 64 (E4).
    """
    sink = MemorySink()
    count, failures = run([ARIA], sink, drop_trailing_marker=True)
    assert count == 1
    assert failures == []
    record = sink.records[0]
    assert record.source_format == "midi"
    assert record.part_index == 0
    assert record.features["min_note"] == "D2"
    assert record.features["max_note"] == "E4"
    assert record.features["tempo_initial_bpm"] == 140.0
    assert record.errors == {}

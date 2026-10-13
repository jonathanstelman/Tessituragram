import os

from songfeat.pipeline import analyze_file, run
from songfeat.sinks.base import MemorySink

ARIA = os.path.join("data", "test_data_arias", "1-I.mid")


def test_one_record_per_part():
    # groups_filter=["basic"]: only part_index is asserted; the borrowed
    # battery (Task 8) has nothing to do with this test.
    records = list(analyze_file(ARIA, groups_filter=["basic"]))
    assert len(records) == 1
    assert records[0].part_index == 0


def test_record_carries_identity_and_features():
    record = next(iter(
        analyze_file(ARIA, groups_filter=["basic"], drop_trailing_marker=True)
    ))
    assert record.source_format == "midi"
    assert record.features["min_note"] == "D2"
    assert record.features["max_note"] == "E4"


def test_piece_scoped_features_are_denormalised_onto_the_record():
    record = next(iter(analyze_file(ARIA, groups_filter=["basic"])))
    assert record.features["tempo_initial_bpm"] == 140.0


def test_multipart_file_yields_one_record_per_part(tmp_path):
    from music21 import corpus, converter
    out = tmp_path / "chorale.musicxml"
    converter.parse(corpus.getWork("bach/bwv66.6")).write("musicxml", fp=str(out))
    records = list(analyze_file(str(out), groups_filter=["basic"]))
    assert len(records) == 4
    assert [r.part_index for r in records] == [0, 1, 2, 3]
    # Pitch ranges differ per part; pooling would make them identical.
    assert len({r.features["min_midi"] for r in records}) > 1


def test_run_reports_failures_without_losing_good_records(tmp_path):
    bad = tmp_path / "broken.mid"
    bad.write_bytes(b"nope")
    sink = MemorySink()
    count, failures = run([str(bad), ARIA], sink, groups_filter=["basic"])
    assert count == 1
    assert len(failures) == 1
    assert "broken.mid" in failures[0][0]


#: Borrowed extractors known to always fail on real input (Task 8): eleven
#: jSymbolic stubs music21 itself has not implemented, plus two native
#: extractors that need data our model/reconstruction cannot supply (Forte
#: triads on a monophonic line; composer metadata for popularity lookup).
#: ``js_beat_histogram`` used to be here too, but it is also structurally a
#: 161-element vector (ruling T) and so moved to SKIPPED_EXTRACTORS instead
#: of surfacing as a runtime error -- it is no longer registered at all.
#: Pinned by name, not just counted, so a regression that breaks a
#: *different*, previously-working extractor is still caught.
EXPECTED_BORROWED_FAILURES = {
    "js_dominant_spread", "js_strong_tonal_centres", "js_glissando_prevalence",
    "js_average_range_of_glissandos", "js_vibrato_prevalence",
    "js_prevalence_of_microtones", "js_number_of_strong_pulses",
    "js_number_of_moderate_pulses", "js_rhythmic_looseness", "js_polyrhythms",
    "js_rhythmic_variability",
    "nat_incorrectly_spelled_triad_prevalence", "nat_composer_popularity",
}


def test_run_through_a_real_sink_produces_a_correct_record():
    """End-to-end on real corpus data, not a hand-built stub (see Task 6 postmortem).

    Independently verified against the MIDI file with music21 directly
    (not via songfeat): the file's only tempo mark is 140bpm at offset 0,
    and its last note is a C1 at offset 476.0 -- the trailing reference
    marker that ``drop_trailing_marker`` strips. Excluding it, the sorted
    MIDI numbers in the file run from 38 (D2) to 64 (E4).

    Runs the full battery (no groups_filter) deliberately: this is the one
    pipeline test that exercises the borrowed jSymbolic/native extractors'
    error path end to end, not just the basic group.
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
    assert set(record.errors) == EXPECTED_BORROWED_FAILURES


def _musicxml_with_lyrics(tmp_path, words):
    """A one-part score with one ``single`` syllable per word."""
    from music21 import note, stream

    part = stream.Part()
    part.id = "Voice"
    for word in words:
        pitch = note.Note("C4", quarterLength=1.0)
        pitch.lyric = word
        part.append(pitch)
    score = stream.Score()
    score.insert(0, part)
    out = tmp_path / "song.musicxml"
    score.write("musicxml", fp=str(out))
    return out


def _musicxml_without_lyrics(tmp_path):
    """A one-part score with notes but no lyrics at all."""
    from music21 import note, stream

    part = stream.Part()
    part.id = "Violin"
    for pitch_name in ("C4", "D4", "E4"):
        part.append(note.Note(pitch_name, quarterLength=1.0))
    score = stream.Score()
    score.insert(0, part)
    out = tmp_path / "instrumental.musicxml"
    score.write("musicxml", fp=str(out))
    return out


def test_the_lyric_text_is_written_to_a_sidecar_file(tmp_path):
    """The row carries a hash and a filename; the words go in a file,
    because a 200-word text in a CSV cell is unusable and Sheets caps a
    cell at 50,000 characters."""
    from songfeat import pipeline
    from songfeat.sinks.files import JsonlSink

    score = _musicxml_with_lyrics(tmp_path, ["Wer", "reitet", "so", "spat"])
    sidecars = tmp_path / "lyrics"
    sink = JsonlSink(str(tmp_path / "o.jsonl"))
    pipeline.run([str(score)], sink, groups_filter=["lyrics"],
                 sidecar_dir=str(sidecars))

    # The name carries the part index (fix round 1, finding 1) so a
    # second lyric-bearing part of the same file never overwrites this
    # one's sidecar.
    written = sidecars / (score.stem + ".part0.txt")
    assert written.exists()
    assert written.read_text(encoding="utf-8") == "Wer reitet so spat\n"


def test_no_sidecar_is_written_when_there_are_no_lyrics(tmp_path):
    from songfeat import pipeline
    from songfeat.sinks.files import JsonlSink

    score = _musicxml_without_lyrics(tmp_path)
    sidecars = tmp_path / "lyrics"
    sink = JsonlSink(str(tmp_path / "o.jsonl"))
    pipeline.run([str(score)], sink, groups_filter=["lyrics"],
                 sidecar_dir=str(sidecars))

    assert not sidecars.exists(), "an empty directory implies a file we failed to write"


def _musicxml_with_two_lyric_parts(tmp_path, first_words, second_words):
    """A duet: two parts, each with its own lyrics."""
    from music21 import note, stream

    score = stream.Score()
    for part_id, words in (("Soprano", first_words), ("Alto", second_words)):
        part = stream.Part()
        part.id = part_id
        for word in words:
            pitch = note.Note("C4", quarterLength=1.0)
            pitch.lyric = word
            part.append(pitch)
        score.insert(0, part)
    out = tmp_path / "duet.musicxml"
    score.write("musicxml", fp=str(out))
    return out


def test_a_duet_writes_one_sidecar_per_part_and_the_columns_match(tmp_path):
    """Fix round 1, finding 1: before the part index was in the name,
    the second part's sidecar write silently overwrote the first's, and
    both rows' lyrics_text_path pointed at a file holding only one
    part's words."""
    from songfeat import pipeline
    from songfeat.sinks.base import MemorySink

    score = _musicxml_with_two_lyric_parts(
        tmp_path, ["high", "note"], ["low", "note"],
    )
    sidecars = tmp_path / "lyrics"
    sink = MemorySink()
    pipeline.run([str(score)], sink, groups_filter=["lyrics"],
                 sidecar_dir=str(sidecars))

    assert len(sink.records) == 2
    paths = [r.features["lyrics_text_path"] for r in sink.records]
    assert len(set(paths)) == 2, "the two parts must not share a filename"
    texts = {
        path: (sidecars / path).read_text(encoding="utf-8") for path in paths
    }
    assert sorted(texts.values()) == ["high note\n", "low note\n"]
    # Every row's column names a file that was actually written, with
    # that row's own words in it -- not the other part's.
    for record in sink.records:
        path = record.features["lyrics_text_path"]
        assert (sidecars / path).exists()


def test_two_different_sources_with_the_same_stem_do_not_overwrite_each_other(
    tmp_path,
):
    """Fix round 1, finding 1: a teacher's real library puts same-named
    pieces (e.g. two settings called "aria.musicxml") in different
    composer directories. The part index alone cannot help here --
    both are part 0 -- so the pipeline's own run-level registry must
    disambiguate by source path instead."""
    from songfeat import pipeline
    from songfeat.sinks.base import MemorySink

    first_dir = tmp_path / "bach"
    second_dir = tmp_path / "handel"
    first_dir.mkdir()
    second_dir.mkdir()
    # _musicxml_with_lyrics always writes "song.musicxml": exactly the
    # same stem in two different directories, which is the point.
    first = _musicxml_with_lyrics(first_dir, ["bach", "words"])
    second = _musicxml_with_lyrics(second_dir, ["handel", "words"])

    sidecars = tmp_path / "lyrics"
    sink = MemorySink()
    pipeline.run([str(first), str(second)], sink, groups_filter=["lyrics"],
                 sidecar_dir=str(sidecars))

    assert len(sink.records) == 2
    paths = [r.features["lyrics_text_path"] for r in sink.records]
    assert len(set(paths)) == 2, "two different sources must not collide on one name"
    written_texts = sorted(
        (sidecars / path).read_text(encoding="utf-8") for path in paths
    )
    assert written_texts == ["bach words\n", "handel words\n"]
    for record in sink.records:
        path = record.features["lyrics_text_path"]
        assert (sidecars / path).exists(), (
            "the column must name a file that was actually written"
        )


def test_an_unwritable_sidecar_directory_still_yields_complete_records(tmp_path):
    """Fix round 1, finding 2: the classification answers in a record's
    features already cost real money by the time the sidecar is
    written. A write failure -- here, sidecar_dir exists as a plain
    file rather than a directory, so os.makedirs raises -- must not
    discard them: the record still comes out, with the failure
    recorded in its own errors, not swallowed as a whole-file failure."""
    from songfeat import pipeline
    from songfeat.sinks.base import MemorySink

    score = _musicxml_with_lyrics(tmp_path, ["love", "me"])
    blocked = tmp_path / "not_a_directory"
    blocked.write_text("in the way")

    sink = MemorySink()
    count, failures = pipeline.run(
        [str(score)], sink, groups_filter=["lyrics"], sidecar_dir=str(blocked)
    )

    assert failures == [], "a sidecar write failure must not fail the whole file"
    assert count == 1
    record = sink.records[0]
    assert record.features["lyrics_word_count"] == 2, (
        "the paid-for classification features must survive the sidecar failure"
    )
    assert "lyrics_sidecar" in record.errors

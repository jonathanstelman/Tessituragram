import os

import music21
import pytest

from songfeat.loaders import (
    DEFAULT_BPM,
    ParseError,
    UnsupportedFormatError,
    build_tempo_map,
    detect_format,
    load,
    quarters_to_seconds,
)
from songfeat.model import Note, TempoMark, Syllable

ARIA = os.path.join("data", "test_data_arias", "1-I.mid")

ABC_TUNE = """X:1
T:Test Tune
M:4/4
L:1/4
K:G
|:G2 AB|c2 BA|G2 AB|c4:|
"""


def test_detect_format_by_extension():
    assert detect_format("a.mid") == "midi"
    assert detect_format("a.MIDI") == "midi"
    assert detect_format("a.mxl") == "musicxml"
    assert detect_format("a.musicxml") == "musicxml"
    assert detect_format("a.abc") == "abc"


def test_detect_format_rejects_unknown():
    with pytest.raises(UnsupportedFormatError):
        detect_format("song.wav")


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load("does-not-exist.mid")


def test_unparseable_file_raises_parse_error(tmp_path):
    bad = tmp_path / "broken.mid"
    bad.write_bytes(b"this is not a midi file")
    with pytest.raises(ParseError):
        load(str(bad))


def test_load_midi():
    """Pinned, not bounded.

    `> 0` on a fixed corpus file could not fail: the values are whatever
    that file contains, and four assertions that a real MIDI has some
    notes somewhere assert nothing about parsing it correctly. Independently
    checked against the file with music21 directly: 455 notes (454 plus the
    trailing C1 marker, which this call keeps), 239 measures, 478 quarters,
    and a single 140bpm mark giving 478 * 60 / 140 = 204.857 seconds.
    """
    piece = load(ARIA)
    assert piece.source_format == "midi"
    assert len(piece.notes) == 455
    assert piece.measure_count == 239
    assert piece.quarter_length == pytest.approx(478.0)
    assert piece.duration_seconds == pytest.approx(204.857, abs=0.001)
    # Notes come back in onset order.
    onsets = [n.onset for n in piece.notes]
    assert onsets == sorted(onsets)


def test_load_abc(tmp_path):
    path = tmp_path / "tune.abc"
    path.write_text(ABC_TUNE)
    piece = load(str(path))
    assert piece.source_format == "abc"
    assert [n.midi for n in piece.notes] == [67, 69, 71, 72, 71, 69, 67, 69, 71, 72]
    assert piece.meters[0].symbol == "4/4"
    assert piece.keys[0].sharps == 1


# --- tempo map -------------------------------------------------------------

def test_tempo_map_defaults_when_no_marks():
    assert build_tempo_map([]) == [(0.0, DEFAULT_BPM)]


def test_tempo_map_backfills_a_late_first_mark():
    mapping = build_tempo_map([TempoMark(onset=8.0, bpm=90.0)])
    assert mapping[0][0] == 0.0


def test_quarters_to_seconds_single_tempo():
    mapping = build_tempo_map([TempoMark(onset=0.0, bpm=120.0)])
    # At 120bpm a quarter note is half a second.
    assert quarters_to_seconds(4, mapping) == pytest.approx(2.0)


def test_quarters_to_seconds_spans_tempo_change():
    mapping = build_tempo_map(
        [TempoMark(onset=0.0, bpm=120.0), TempoMark(onset=4.0, bpm=60.0)]
    )
    # 4 quarters at 120 (2s) then 4 quarters at 60 (4s).
    assert quarters_to_seconds(8, mapping) == pytest.approx(6.0)


def test_quarters_to_seconds_at_zero():
    assert quarters_to_seconds(0, build_tempo_map([])) == 0.0


# --- the Tessituragram C1 reference marker ---------------------------------

def test_marker_is_kept_by_default():
    piece = load(ARIA)
    assert min(n.midi for n in piece.notes) == 24


def test_marker_is_dropped_on_request():
    piece = load(ARIA, drop_trailing_marker=True)
    assert min(n.midi for n in piece.notes) > 24


def test_marker_removal_preserves_genuine_low_notes():
    """A piece that really uses C1 should keep every note."""
    from songfeat.loaders import _drop_trailing_marker

    notes = [
        Note(midi=24, onset=0.0, duration=1.0, part=0),
        Note(midi=60, onset=1.0, duration=1.0, part=0),
        Note(midi=24, onset=2.0, duration=1.0, part=0),
    ]
    survivors, dropped = _drop_trailing_marker(notes)
    assert survivors == notes
    assert dropped is None


def test_marker_removal_on_empty_input():
    from songfeat.loaders import _drop_trailing_marker

    survivors, dropped = _drop_trailing_marker([])
    assert survivors == []
    assert dropped is None


def test_marker_removal_on_marker_only_part():
    """A part that is nothing but the marker must not raise, and reports it."""
    from songfeat.loaders import _drop_trailing_marker

    notes = [Note(midi=24, onset=5.0, duration=1.0, part=0)]
    survivors, dropped = _drop_trailing_marker(notes)
    assert survivors == []
    assert dropped is notes[0]


# --- dropping the marker must also shorten the piece ----------------------
#
# The corpus files all end with a C1 marker whose *time* music21 still
# counts even once _drop_trailing_marker discards its pitch. Reference
# numbers below are measured straight off the spec's ground-truth table for
# aria I (data/test_data_arias/1-I.mid), not derived from our own code.

def test_dropping_marker_truncates_to_marker_onset():
    piece = load(ARIA, drop_trailing_marker=True)
    assert piece.quarter_length == 476.0
    assert piece.duration_seconds == pytest.approx(204.0, abs=0.01)


def test_keeping_marker_leaves_duration_untouched():
    piece = load(ARIA, drop_trailing_marker=False)
    assert piece.quarter_length == 478.0
    assert piece.duration_seconds == pytest.approx(204.857, abs=0.01)


def test_dropping_marker_gives_reference_rest_time():
    piece = load(ARIA, drop_trailing_marker=True)
    sounding = sum(n.duration_seconds for n in piece.notes)
    rest = piece.duration_seconds - sounding
    assert rest == pytest.approx(39.43, abs=0.01)


def test_genuine_trailing_low_c1_leaves_extent_untouched(tmp_path):
    """When another note also sits at or below C1, nothing is dropped, and
    the piece's extent must be left exactly as the parser gave it."""
    from music21 import note as m21_note
    from music21 import stream as m21_stream

    s = m21_stream.Stream()
    s.append(m21_note.Note("C4", quarterLength=1.0))
    s.append(m21_note.Note("C1", quarterLength=1.0))
    s.append(m21_note.Note("C1", quarterLength=1.0))
    out = tmp_path / "genuine_low_c1.musicxml"
    s.write("musicxml", fp=str(out))

    kept = load(str(out), drop_trailing_marker=False)
    dropped = load(str(out), drop_trailing_marker=True)

    assert min(n.midi for n in dropped.notes) == 24
    assert dropped.quarter_length == kept.quarter_length
    assert dropped.duration_seconds == pytest.approx(kept.duration_seconds)


def test_no_marker_leaves_extent_untouched(tmp_path):
    path = tmp_path / "tune.abc"
    path.write_text(ABC_TUNE)

    kept = load(str(path), drop_trailing_marker=False)
    dropped = load(str(path), drop_trailing_marker=True)

    assert dropped.quarter_length == kept.quarter_length
    assert dropped.duration_seconds == pytest.approx(kept.duration_seconds)


def test_multipart_truncates_to_the_later_dropped_marker(tmp_path):
    """Two parts each drop their own marker at a different onset; the piece
    must truncate to whichever onset is later, not to either part alone."""
    from music21 import note as m21_note
    from music21 import stream as m21_stream

    part_a, part_b = m21_stream.Part(), m21_stream.Part()
    for i, midi in enumerate((60, 62, 64)):
        n = m21_note.Note(midi)
        n.quarterLength = 1.0
        part_a.insert(float(i), n)
    marker_a = m21_note.Note(24)
    marker_a.quarterLength = 1.0
    part_a.insert(3.0, marker_a)

    for i, midi in enumerate((55, 57)):
        n = m21_note.Note(midi)
        n.quarterLength = 1.0
        part_b.insert(float(i), n)
    marker_b = m21_note.Note(24)
    marker_b.quarterLength = 1.0
    part_b.insert(6.0, marker_b)

    out = tmp_path / "two_markers.mid"
    m21_stream.Score([part_a, part_b]).write("midi", fp=str(out))

    kept = load(str(out), drop_trailing_marker=False)
    dropped = load(str(out), drop_trailing_marker=True)

    assert kept.quarter_length == 8.0
    assert dropped.quarter_length == 6.0
    # Both parts actually dropped their marker, not just the one that wins.
    assert all(min(p.notes, key=lambda n: n.midi).midi > 24 for p in dropped.parts)


def test_marker_only_part_loads_through_the_full_pipeline(tmp_path):
    """A part that is nothing but the marker must still load without raising,
    collapsing to an empty, zero-length piece."""
    from music21 import note as m21_note
    from music21 import stream as m21_stream

    part = m21_stream.Part()
    marker = m21_note.Note(24)
    marker.quarterLength = 1.0
    part.insert(0.0, marker)

    out = tmp_path / "marker_only.mid"
    m21_stream.Score([part]).write("midi", fp=str(out))

    piece = load(str(out), drop_trailing_marker=True)

    assert piece.notes == []
    assert piece.quarter_length == 0.0
    assert piece.duration_seconds == 0.0


# --- per-part isolation -----------------------------------------------------

def test_multipart_file_keeps_parts_separate(tmp_path):
    from music21 import corpus, converter

    out = tmp_path / "chorale.musicxml"
    converter.parse(corpus.getWork("bach/bwv66.6")).write("musicxml", fp=str(out))
    piece = load(str(out))
    assert len(piece.parts) == 4
    assert all(not p.is_empty for p in piece.parts)
    # Soprano sits above bass; pooling would hide this.
    assert max(n.midi for n in piece.parts[0].notes) > max(
        n.midi for n in piece.parts[3].notes
    )


# --- multi-tune (Opus) files ------------------------------------------------

#: music21 bundles O'Neill's 1850, whose .abc files each hold many tunes.
#: A real multi-tune file is the point here: a synthesised two-tune string
#: would not prove music21 still returns an Opus for the shape in the wild.
MULTI_TUNE_ABC = os.path.join(
    os.path.dirname(music21.__file__), "corpus", "oneills1850", "0351-0400.abc"
)


def test_multi_tune_abc_is_refused_rather_than_pooled():
    """A multi-tune file must not become one record.

    Before this guard, music21's Opus was wrapped whole: 50 unrelated
    tunes pooled into one part of 4240 notes, a 31-semitone
    "compositional range" against 17-20 per tune, and a 1358-second
    "duration". Every tessitura quartile and passaggio dwell was computed
    across the lot, with no error, warning or null to show it.
    """
    from music21 import converter, stream

    parsed = converter.parse(MULTI_TUNE_ABC)
    # Guards the test: if music21 ever returns a Score here, the Opus
    # branch is unreachable and this test would pass without exercising it.
    assert isinstance(parsed, stream.Opus), type(parsed).__name__
    assert len(parsed.scores) == 50

    with pytest.raises(ParseError) as caught:
        load(MULTI_TUNE_ABC)
    message = str(caught.value)
    assert "50" in message, message
    assert "multi" in message.lower() or "opus" in message.lower(), message


def test_single_tune_abc_still_loads():
    """The Opus guard must not reject valid single-tune ABC."""
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "tune.abc")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(ABC_TUNE)
        piece = load(path)
    assert [n.midi for n in piece.notes] == [67, 69, 71, 72, 71, 69, 67, 69, 71, 72]


# --- lyrics ----------------------------------------------------------------


def test_loader_captures_all_verses_from_musicxml(tmp_path):
    """music21's ``element.lyric`` returns verse 1 only, so the loader has
    to read ``element.lyrics`` to see the rest."""
    from music21 import note as m21_note, stream

    part = stream.Part()
    first = m21_note.Note("C4", quarterLength=1.0)
    first.addLyric("Ky", applyRaw=True)
    first.addLyric("Lord", applyRaw=True)       # verse 2
    second = m21_note.Note("D4", quarterLength=1.0)
    second.addLyric("ri", applyRaw=True)
    second.addLyric("have", applyRaw=True)
    part.append([first, second])
    score = stream.Score([part])
    path = tmp_path / "two-verses.musicxml"
    score.write("musicxml", fp=str(path))

    piece = load(str(path))
    notes = piece.parts[0].notes

    assert [s.number for s in notes[0].lyrics] == [1, 2]
    assert [s.text for s in notes[0].lyrics] == ["Ky", "Lord"]
    assert notes[0].lyric == "Ky", "verse-1 convenience text is unchanged"
    assert [s.text for s in notes[1].lyrics] == ["ri", "have"]


def test_loader_uses_lowest_verse_when_verse_1_is_absent(tmp_path):
    """When verses are numbered starting at 2+, Note.lyric derives from the
    lowest-numbered verse present, not from music21's multi-verse fallback."""
    # Create a minimal MusicXML with a lyric starting at verse 2
    # (manually constructed XML since music21's addLyric always creates sequential verses)
    musicxml = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE score-partwise PUBLIC "-//Musicnerd//DTD MusicXML 3.1 Partwise//EN"
 "http://www.musicxml.org/partwise.dtd">
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1">
      <part-name>Part 1</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>4</duration>
        <type>quarter</type>
        <lyric number="2">
          <syllabic>single</syllabic>
          <text>Wer</text>
        </lyric>
      </note>
    </measure>
  </part>
</score-partwise>"""

    path = tmp_path / "verse-2-only.musicxml"
    path.write_text(musicxml)

    piece = load(str(path))
    note = piece.parts[0].notes[0]

    assert [s.number for s in note.lyrics] == [2]
    assert note.lyric == "Wer", "lyric derives from lowest-numbered verse (2), not music21's fallback"

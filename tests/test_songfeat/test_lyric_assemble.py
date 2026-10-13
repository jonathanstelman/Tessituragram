"""Assembly turns per-note syllables back into text.

Every expected string here is written out in full rather than computed,
so that a change in the joining rules fails loudly instead of agreeing
with whatever the code now does.
"""

from songfeat.features.lyrics.assemble import (
    LyricText, assemble_text, normalise, text_sha256,
)
from songfeat.model import Note, Part, Piece, Syllable


def built(*rows):
    """rows of (midi, (verse, text, syllabic)) -> a Part."""
    notes = []
    for index, (midi, *syllables) in enumerate(rows):
        notes.append(Note(
            midi=midi, onset=float(index), duration=1.0, part=0,
            lyric=syllables[0][1] if syllables else None,
            lyrics=tuple(
                Syllable(number=v, text=t, syllabic=s) for v, t, s in syllables
            ),
        ))
    return Part(index=0, name="Voice", notes=notes)


def test_syllabic_markers_join_one_word_across_four_notes():
    part = built(
        (60, (1, "Er", "begin")),
        (62, (1, "l", "middle")),
        (64, (1, "kö", "middle")),
        (65, (1, "nig", "end")),
    )
    assert assemble_text(part).text == "Erlkönig\n"


def test_single_markers_stay_separate_words():
    part = built((60, (1, "Wer", "single")), (62, (1, "reitet", "single")))
    assert assemble_text(part).text == "Wer reitet\n"


def test_each_verse_becomes_its_own_line_in_number_order():
    part = built(
        (60, (1, "Ky", "begin"), (2, "Lord", "single")),
        (62, (1, "rie", "end"), (2, "have", "single")),
    )
    result = assemble_text(part)
    assert result.text == "Kyrie\nLord have\n"
    assert result.verse_count == 2
    # Three words total: "Kyrie" (verse 1) plus "Lord" and "have" (verse 2).
    # The brief's pinned value here was 4, which no consistent definition
    # of word_count satisfies alongside the other pinned tests (e.g. the
    # "Hal"+"lo" -> "Hallo" feature test, which pins word_count == 1 for a
    # single merged word). Corrected to 3; see task-2-report.md.
    assert result.word_count == 3


def test_verse_numbers_that_skip_are_counted_as_found_not_assumed():
    """Review Focus 1: a score may carry number="2" and number="4" with
    no number="1" or "3". Nothing may invent the missing verses."""
    part = built((60, (2, "two", "single")), (62, (4, "four", "single")))
    result = assemble_text(part)
    assert result.verse_count == 2, "two distinct numbers were present"
    assert result.text == "two\nfour\n", "no blank lines for the gaps"


def test_an_extend_marker_contributes_no_text():
    part = built(
        (60, (1, "Ah", "single")),
        (62, (1, "", None)),
    )
    assert assemble_text(part).text == "Ah\n"
    assert assemble_text(part).word_count == 1


def test_an_elision_joins_two_syllables_sung_on_one_note():
    """MusicXML <elision> puts two syllables on one note, which is how
    Italian and French vocal lines are written. Both arrive as separate
    Syllable entries on the same note and the same verse."""
    notes = [
        Note(midi=60, onset=0.0, duration=1.0, part=0, lyric="del",
             lyrics=(Syllable(number=1, text="del", syllabic="single"),
                     Syllable(number=1, text="l'al", syllabic="begin"))),
        Note(midi=62, onset=1.0, duration=1.0, part=0, lyric="ma",
             lyrics=(Syllable(number=1, text="ma", syllabic="end"),)),
    ]
    part = Part(index=0, name="Voice", notes=notes)
    assert assemble_text(part).text == "del l'alma\n"


def test_a_repeated_section_contributes_its_text_once():
    """Repeats are not expanded: the text is taken as notated, once. A
    repeated verse adds no information and would distort word counts."""
    part = built((60, (1, "once", "single")), (62, (1, "only", "single")))
    assert assemble_text(part).word_count == 2


def test_a_part_with_no_lyrics_at_all_assembles_to_none():
    """Review Focus 2: None, never an empty LyricText, which would read
    as "we read this song and found no words"."""
    part = Part(index=0, name="Violin", notes=[
        Note(midi=60, onset=0.0, duration=1.0, part=0),
    ])
    assert assemble_text(part) is None


def test_a_part_with_no_notes_assembles_to_none():
    assert assemble_text(Part(index=0, name="Voice", notes=[])) is None


def test_a_whitespace_only_syllable_contributes_no_word():
    """Fix round 1, Finding 1: a space passes the ``not syllable.text``
    guard -- it is a non-empty string -- so it must not be counted as a
    word. The syllable still marks that a verse was present in the
    source, so the result is a real (if blank) ``LyricText``, not
    ``None`` -- distinguishing "lyrics present but empty after
    reassembly" from "no lyric events at all" is the service layer's
    job, and it can only make that distinction if this function tells
    the truth about what it found."""
    part = built((60, (1, " ", "single")))
    result = assemble_text(part)
    assert result is not None, "a lyric event, even a blank one, is not absence"
    assert result.word_count == 0
    assert result.text == ""


def test_normalisation_is_pinned_because_the_cache_key_depends_on_it():
    raw = "Café  \r\nnext line   \r\n\r\n"
    assert normalise(raw) == "Café\nnext line\n"


def test_the_hash_is_of_the_normalised_text():
    assert text_sha256("Café\n") == text_sha256("Café  \r\n")


def test_the_hash_is_the_sha256_of_the_exact_normalised_bytes():
    """Pinned against an independent computation rather than a magic
    constant: this fails if normalise() ever emits different bytes,
    which is what the cache key depends on."""
    import hashlib

    expected = hashlib.sha256("Erlkönig\n".encode("utf-8")).hexdigest()
    assert text_sha256("Erlkönig") == expected
    assert text_sha256("Erlkönig  \r\n\r\n") == expected


def test_the_lyrics_text_feature_reports_the_counts_and_the_hash():
    from songfeat.features import base

    part = built((60, (1, "Hal", "begin")), (62, (1, "lo", "end")))
    piece = Piece(source_path="/tmp/greeting.musicxml",
                  source_format="musicxml", parts=[part])
    out = base.extract_part(part, piece, groups_filter=["lyrics"])

    assert out["lyrics_word_count"] == 1
    assert out["lyrics_verse_count"] == 1
    assert out["lyrics_sha256"] == text_sha256("Hallo\n")
    assert out["lyrics_text_path"] == "greeting.txt"
    assert out["lyrics_undefined_reason"] is None


def test_the_lyrics_text_feature_is_null_with_a_reason_on_a_part_with_no_lyrics():
    from songfeat.features import base

    part = Part(index=0, name="Violin", notes=[
        Note(midi=60, onset=0.0, duration=1.0, part=0),
    ])
    piece = Piece(source_path="/tmp/quartet.mid",
                  source_format="midi", parts=[part])
    out = base.extract_part(part, piece, groups_filter=["lyrics"])

    for field in ("lyrics_word_count", "lyrics_verse_count",
                  "lyrics_sha256", "lyrics_text_path"):
        assert out[field] is None, field
    assert out["lyrics_undefined_reason"] == (
        "this part carries no lyric events; lyric features need a "
        "lyric-bearing format such as MusicXML"
    )

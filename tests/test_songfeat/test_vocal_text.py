import pytest

from songfeat.features import base
from songfeat.model import Note, Part, Piece


def built(pairs) -> tuple[Part, Piece]:
    """pairs are (midi, lyric_or_None)."""
    notes = [
        Note(midi=m, onset=float(i), duration=1.0, part=0,
             onset_seconds=i * 0.5, duration_seconds=0.5, lyric=lyric)
        for i, (m, lyric) in enumerate(pairs)
    ]
    part = Part(index=0, notes=notes)
    return part, Piece(source_path="x.mid", source_format="midi",
                       parts=[part], duration_seconds=len(pairs) * 0.5)


def test_syllables_are_counted_from_lyric_events():
    part, piece = built([(60, "I"), (62, "met"), (64, "my")])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_syllables"] == 3


def test_one_note_per_syllable_has_no_melisma():
    part, piece = built([(60, "I"), (62, "met")])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_melismas"] == 0
    assert out["melisma_share"] == 0.0
    assert out["notes_per_syllable"] == pytest.approx(1.0)


def test_a_melisma_is_notes_continuing_one_syllable():
    part, piece = built([(60, "Glo"), (62, None), (64, None), (65, "ri")])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_melismas"] == 1
    assert out["melisma_longest_notes"] == 3
    assert out["notes_per_syllable"] == pytest.approx(2.0)


def test_melisma_share_is_a_fraction_of_notes():
    part, piece = built([(60, "a"), (62, None), (64, "b"), (65, "c")])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["melisma_share"] == pytest.approx(0.5)


def test_a_part_without_lyrics_yields_none():
    part, piece = built([(60, None), (62, None)])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_syllables"] == 0
    assert out["notes_per_syllable"] is None


def test_empty_part_yields_none():
    part = Part(index=0)
    piece = Piece(source_path="x.mid", source_format="midi", parts=[part])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_syllables"] is None


# --- Ruling AA: notes before the first lyric belong to no syllable ---
#
# A leading lyric-less note (an instrumental pickup, or a staff where
# lyrics begin partway through) must not open a phantom group that
# "owns" the notes before the first real syllable: that would both
# overcount groups relative to n_syllables and, worse, could report a
# melisma over a stretch that has no text at all.

def test_leading_unlyriced_notes_do_not_fabricate_a_melisma():
    # Three lyric-less notes followed by a single syllable: with the
    # buggy "not groups" grouping this becomes a fabricated 3-note
    # melisma on a syllable that doesn't exist. Ruling AA excludes the
    # leading notes from melisma grouping entirely.
    part, piece = built([(60, None), (62, None), (64, None), (65, "Ky")])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_syllables"] == 1
    assert out["n_melismas"] == 0
    assert out["melisma_longest_notes"] == 1
    assert out["melisma_share"] == 0.0
    assert out["notes_per_syllable"] == pytest.approx(1.0)


def test_leading_unlyriced_notes_are_excluded_not_merged():
    # ["Ky", "ri", "e"] with a leading pickup note: 3 syllables, no
    # melisma. The buggy grouping would instead merge the pickup note
    # into a group with the final syllable's continuation, producing
    # len(groups) != n_syllables.
    part, piece = built([
        (59, None), (60, "Ky"), (62, "ri"), (64, "e"), (65, None), (67, None),
    ])
    out = base.extract_part(part, piece, groups_filter=["vocal"])
    assert out["n_syllables"] == 3
    assert out["n_melismas"] == 1
    assert out["melisma_longest_notes"] == 3
    assert out["notes_per_syllable"] == pytest.approx(5 / 3, abs=1e-3)


def test_real_corpus_aria_has_no_lyrics():
    # Pinned finding: the corpus carries zero lyric events. This is the
    # documented reality of the dataset, not a loader gap — if a future
    # loader starts extracting lyrics, this test fails loudly and should
    # be updated deliberately rather than silently drifting.
    from songfeat.loaders import load
    piece = load("data/test_data_arias/1-I.mid")
    out = base.extract_part(piece.parts[0], piece, groups_filter=["vocal"])
    assert out["n_syllables"] == 0
    assert out["notes_per_syllable"] is None
    assert out["melisma_longest_notes"] is None
    assert out["melisma_share"] is None
    assert out["n_melismas"] is None
    assert out["syllables_per_second"] is None

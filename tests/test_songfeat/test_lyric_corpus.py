"""The corpus is frozen data; these tests guard its shape, not its content."""

import json
import pathlib

from songfeat.features.lyrics.assemble import assemble_text
from songfeat.loaders import load

CORPUS = pathlib.Path(__file__).parents[1] / "data" / "lyrics_corpus"

#: The corpus is frozen, so its total assembled word count is a known
#: constant rather than a floor: a song silently losing its lyrics would
#: still clear a per-song minimum.
TOTAL_WORDS = 1097


def _labels():
    return json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))


def test_there_are_thirty_six_songs_and_every_one_has_a_score():
    slugs = sorted(p.stem for p in CORPUS.glob("*.musicxml"))
    assert len(slugs) == 36, slugs


def test_every_song_is_labelled_and_every_label_names_a_song():
    slugs = {p.stem for p in CORPUS.glob("*.musicxml")}
    labels = _labels()
    assert set(labels["labels"]) == slugs
    assert set(labels["split"]["dev"]) | set(labels["split"]["held_out"]) == slugs


def test_the_split_is_twenty_four_and_twelve_and_disjoint():
    split = _labels()["split"]
    assert len(split["dev"]) == 24
    assert len(split["held_out"]) == 12
    assert not set(split["dev"]) & set(split["held_out"])


def test_every_score_round_trips_to_assemblable_text():
    """A generated file nobody can read is worse than no corpus."""
    checked = 0
    words = 0
    for path in sorted(CORPUS.glob("*.musicxml")):
        piece = load(str(path))
        assembled = assemble_text(piece.parts[0])
        assert assembled is not None, path.name
        assert assembled.word_count >= 15, (path.name, assembled.word_count)
        words += assembled.word_count
        checked += 1
    assert checked == 36, "every song must be read, not just the ones that parse"
    assert words == TOTAL_WORDS, (words, TOTAL_WORDS)


def test_the_bystander_song_has_no_relational_focus_label():
    """Pins the Tom's Diner case: the label itself must say false, or the
    corpus does not contain the case the spec says it contains."""
    label = _labels()["labels"]["bystanders"]["perspective"]
    assert label["relational_focus_present"] is False
    assert label["love_interest_gender"] is None


def test_the_clean_child_song_is_labelled_zero_on_every_advisory():
    advisories = _labels()["labels"]["advisory-clean-child"]["advisories"]
    assert advisories and set(advisories.values()) == {0}

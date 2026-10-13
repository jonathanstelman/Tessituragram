import pytest

from songfeat import validation_lyrics as vl
from songfeat.features.lyrics import service
from songfeat.features.lyrics.client import FakeJevClient
from songfeat.features.lyrics.questions import Answer

CORPUS = "tests/data/lyrics_corpus"


@pytest.fixture(autouse=True)
def _clean():
    service.reset()
    yield
    service.reset()


def test_a_perfect_classifier_agrees_on_every_labelled_column(tmp_path):
    """Built by reading the labels back as answers: proves the harness
    can report agreement, and that its comparison is the right way
    round."""
    service.configure(client=vl.oracle_client(CORPUS, "dev"),
                      cache=None, question_set_name="full")
    results = vl.compare_corpus(CORPUS, "dev")
    assert results, "the harness found no columns to compare"
    for result in results:
        assert result.agreed == result.of, (result.column, result.disagreements)


def test_a_classifier_that_answers_no_to_everything_disagrees_and_says_where():
    service.configure(
        client=FakeJevClient({}),  # every question unscripted -> errored
        cache=None, question_set_name="full",
    )
    results = vl.compare_corpus(CORPUS, "dev")
    themes = next(r for r in results if r.column == "theme_love")
    assert themes.agreed < themes.of
    assert themes.disagreements, "a disagreement must name the songs"
    assert all(isinstance(slug, str) for slug in themes.disagreements)


def test_the_report_is_per_column_and_never_one_composite():
    """The axes will not be equally learnable, and an average hides
    that."""
    assert not hasattr(vl, "overall_agreement")
    source = open("songfeat/validation_lyrics.py", encoding="utf-8").read()
    assert "upper bound" in source, (
        "the harness must carry the caveat that single-author songs, "
        "labels and question wording make these figures an upper bound"
    )


def test_the_two_splits_are_reported_separately_and_held_out_is_thirteen():
    # The brief's own Step 1 code pins this at 12; the frozen corpus
    # (tests/data/lyrics_corpus/labels.json["split"]["held_out"]) lists
    # 13 slugs, matching the brief's own prose ("dev 24, held-out 13")
    # and the "Done when" criterion below. 12 is the plan's stale
    # arithmetic the global constraints warn about; pinning the value
    # actually in the frozen, do-not-modify corpus instead.
    assert len(vl.slugs_for(CORPUS, "dev")) == 24
    assert len(vl.slugs_for(CORPUS, "held-out")) == 13


def test_an_unknown_split_raises_rather_than_defaulting_to_everything():
    with pytest.raises(ValueError, match="unknown split"):
        vl.slugs_for(CORPUS, "all")

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


def test_every_frozen_theme_label_key_maps_onto_a_column():
    """UNMAPPABLE_LABEL_KEYS must be empty for the frozen corpus.

    Fix round 1: two frozen label keys (``religion_devotional``,
    ``activities_eating``) spell the same compound child name in the
    spec differently from the vocabulary's own slug and were, before
    this fix, silently dropped from every comparison rather than
    aliased -- which inflates apparent coverage instead of flagging a
    real gap. This pins the post-fix state: scanning every label in
    both splits leaves nothing unmapped.
    """
    vl.UNMAPPABLE_LABEL_KEYS.clear()
    labels = vl._labels(CORPUS)["labels"]
    assert labels, "the harness found no labelled songs to scan"
    for record in labels.values():
        vl._theme_columns(record.get("themes", {}))
    assert vl.UNMAPPABLE_LABEL_KEYS == set(), vl.UNMAPPABLE_LABEL_KEYS


# --- what the harness can actually score (fix wave, I5) -------------------

def test_the_score_columns_are_compared_within_a_tolerance():
    """``_agrees`` compared int labels by exact equality, so all nine
    advisory intensities and all thirteen centralities were matched
    against a probability-weighted mean with ``==``. A real run returned
    ``advisory_violence = 0.64`` and
    ``sensitive_loss_of_parent_centrality = 4.72``: neither equals any
    integer, so the first real agreement table would have read near-zero
    on twenty-two columns for purely arithmetic reasons. The oracle hid
    it by returning ``float(label)``."""
    assert vl.SCORE_TOLERANCE == 0.5
    assert len(vl.SCORE_COLUMNS) == 22, (
        "nine advisory intensities and thirteen centralities"
    )
    assert "advisory_violence" in vl.SCORE_COLUMNS
    assert "sensitive_loss_of_parent_centrality" in vl.SCORE_COLUMNS
    # A modifier is a probability, not a Score: it must keep the
    # boolean comparison.
    assert "advisory_violence_depicted" not in vl.SCORE_COLUMNS

    # The two values a real run actually returned.
    assert vl._agrees(0.64, 1, vl.SCORE_TOLERANCE) is True
    assert vl._agrees(4.72, 5, vl.SCORE_TOLERANCE) is True
    # Still able to disagree: half a level, not any level.
    assert vl._agrees(0.64, 0, vl.SCORE_TOLERANCE) is False
    assert vl._agrees(4.72, 4, vl.SCORE_TOLERANCE) is False
    # And without a tolerance the comparison is still exact.
    assert vl._agrees(0.64, 1) is False


def test_a_real_valued_score_agrees_through_compare_corpus():
    """End to end: a client answering every Score 0.4 above its label
    agrees on the Score columns, which with exact equality it could not.
    """
    labels = vl._labels(CORPUS)["labels"]

    class _NearMiss:
        model = "near/miss"
        resolved_model = None
        calls_made = 0

        def ask(self, state, questions):
            slug = vl._slug_for_text(CORPUS, state)
            expected = vl._expected_columns(labels[slug])
            out = []
            for question in questions:
                answer = vl._answer_for(question, expected.get(question.column))
                if answer.score is not None:
                    answer = type(answer)(question.id, score=answer.score + 0.4)
                out.append(answer)
            return out

    service.configure(client=_NearMiss(), cache=None, question_set_name="full")
    results = {r.column: r for r in vl.compare_corpus(CORPUS, "dev")}
    scored = [results[column] for column in sorted(vl.SCORE_COLUMNS)]
    assert len(scored) == 22
    for result in scored:
        assert result.agreed == result.of, (result.column, result.disagreements)


def test_the_derived_columns_are_in_the_comparison():
    """``age_band``, ``age_band_driver`` and the nine theme divergence
    columns were absent from the comparison entirely. Both are derived
    by a documented rule, so the expectation is that rule applied to the
    labels -- which is what makes scoring them meaningful rather than
    circular."""
    service.configure(client=vl.oracle_client(CORPUS, "dev"),
                      cache=None, question_set_name="full")
    results = {r.column: r for r in vl.compare_corpus(CORPUS, "dev")}

    assert "age_band" in results
    assert "age_band_driver" in results
    assert "age_band_rule" not in results, (
        "the rule version is not a reading of the song"
    )
    divergences = sorted(c for c in results if c.endswith("_divergence"))
    assert len(divergences) == 9, divergences
    for column in ["age_band", "age_band_driver", *divergences]:
        assert results[column].of == 24, column


def test_the_language_column_is_reported_as_unlabelled_not_silently_skipped():
    """The frozen corpus carries no language label, and inventing one
    here ("English except the Italian one") would be the harness
    labelling its own exam. So it is named in the output instead."""
    assert set(vl.UNLABELLED_COLUMNS) == {"lyrics_language"}

    service.configure(client=vl.oracle_client(CORPUS, "dev"),
                      cache=None, question_set_name="full")
    results = {r.column for r in vl.compare_corpus(CORPUS, "dev")}
    assert "lyrics_language" not in results


def test_the_report_states_the_tolerance_it_used(capsys):
    service.configure(client=vl.oracle_client(CORPUS, "dev"),
                      cache=None, question_set_name="full")
    vl.print_agreement(CORPUS, "dev")
    printed = capsys.readouterr().out
    assert "+/-0.5" in printed
    assert "not compared at all, for want of a label:" in printed
    assert "lyrics_language" in printed

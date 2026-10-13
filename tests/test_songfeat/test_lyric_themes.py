from songfeat.features.lyrics import themes
from songfeat.features.lyrics.questions import Answer, Kind


def test_the_vocabulary_is_nine_families_and_fifty_six_children():
    from songfeat.features.lyrics.vocabulary import THEMES

    assert len(THEMES) == 9
    children = sum(len(kids) for _, kids in THEMES.values())
    assert children == 56


def test_there_are_sixty_five_questions_and_seventy_four_columns():
    assert len(themes.QUESTIONS) == 65
    assert len(themes.THEME_FIELDS) == 74


def test_no_child_slug_repeats_its_family_name():
    """theme_love_love_lost would be the column name if one did."""
    from songfeat.features.lyrics.vocabulary import THEMES

    checked = 0
    for family, (_, kids) in THEMES.items():
        for slug, _text in kids:
            checked += 1
            assert not slug.startswith(family), f"{family}/{slug}"
    assert checked == 56


def test_every_question_is_a_noul_because_themes_are_multi_label():
    assert {question.kind for question in themes.QUESTIONS} == {Kind.NOUL}


def test_columns_from_passes_through_probabilities():
    answers = {"theme_love": Answer("theme_love", probability=0.91)}
    out = themes.columns_from(answers)
    assert out["theme_love"] == 0.91
    assert out["theme_nature"] is None, "unasked stays null, never 0.0"


def test_divergence_is_true_when_the_family_fires_but_no_child_does():
    answers = {"theme_love": Answer("theme_love", probability=0.90)}
    answers.update({
        f"theme_love_{slug}": Answer(f"theme_love_{slug}", probability=0.10)
        for slug in ("courtship", "desire", "devotion", "unrequited",
                     "parting", "complicated", "lost")
    })
    out = themes.columns_from(answers)
    assert out["theme_love_divergence"] == 1.0


def test_divergence_is_true_when_a_child_fires_but_the_family_does_not():
    answers = {"theme_love": Answer("theme_love", probability=0.10)}
    answers.update({
        f"theme_love_{slug}": Answer(f"theme_love_{slug}", probability=0.10)
        for slug in ("courtship", "desire", "devotion", "parting",
                     "complicated", "lost")
    })
    answers["theme_love_unrequited"] = Answer("theme_love_unrequited", probability=0.88)
    out = themes.columns_from(answers)
    assert out["theme_love_divergence"] == 1.0


def test_divergence_is_false_when_family_and_child_agree():
    answers = {"theme_love": Answer("theme_love", probability=0.91)}
    answers.update({
        f"theme_love_{slug}": Answer(f"theme_love_{slug}", probability=0.10)
        for slug in ("courtship", "desire", "devotion", "parting",
                     "complicated", "lost")
    })
    answers["theme_love_unrequited"] = Answer("theme_love_unrequited", probability=0.88)
    out = themes.columns_from(answers)
    assert out["theme_love_divergence"] == 0.0


def _other_child_columns(exclude: str) -> list[str]:
    """Every theme_<family>_<slug> column except ``exclude``."""
    from songfeat.features.lyrics.vocabulary import THEMES

    return [
        f"theme_{family}_{slug}"
        for family, (_, kids) in THEMES.items()
        for slug, _text in kids
        if f"theme_{family}_{slug}" != exclude
    ]


def test_partial_coverage_agrees_is_not_a_divergence():
    """What a core run produces when the song is about unrequited love:
    CORE_IDS answers only theme_love and theme_love_unrequited, leaving
    the love family's other six children and every other family's
    children absent. The family fired, the one known child agrees, so
    there is no divergence."""
    answers = {
        "theme_love": Answer("theme_love", probability=0.90),
        "theme_love_unrequited": Answer("theme_love_unrequited", probability=0.85),
    }
    out = themes.columns_from(answers)

    assert out["theme_love"] == 0.90
    assert out["theme_love_unrequited"] == 0.85

    other_children = _other_child_columns(exclude="theme_love_unrequited")
    assert len(other_children) == 55
    assert all(out[column] is None for column in other_children), (
        "absent children must stay null, never 0.0"
    )

    assert out["theme_love_divergence"] == 0.0


def test_partial_coverage_with_the_known_child_low_is_a_divergence():
    """What a core run produces when the song is about a kind of love
    that is not unrequited: the family fires but the only child asked
    reads low, and every other child is absent and so excluded from
    'known'. This is exactly the case theme_love_divergence exists to
    surface -- the subject falls between the leaves."""
    answers = {
        "theme_love": Answer("theme_love", probability=0.90),
        "theme_love_unrequited": Answer("theme_love_unrequited", probability=0.10),
    }
    out = themes.columns_from(answers)
    assert out["theme_love_divergence"] == 1.0


def test_partial_coverage_with_the_known_child_high_is_a_divergence_the_other_way():
    """A core run where the family reads low but the one child asked
    fires -- the mirror image of the previous case, with the same
    'rest absent' shape CORE_IDS always produces."""
    answers = {
        "theme_love": Answer("theme_love", probability=0.10),
        "theme_love_unrequited": Answer("theme_love_unrequited", probability=0.88),
    }
    out = themes.columns_from(answers)
    assert out["theme_love_divergence"] == 1.0


def test_divergence_is_null_when_the_family_was_not_asked():
    """A core run asks two theme questions. Divergence over absent
    answers is undefined, not false."""
    out = themes.columns_from({})
    assert out["theme_love_divergence"] is None


def test_the_feature_is_null_with_a_reason_when_no_client_is_configured():
    from songfeat.features import base
    from songfeat.model import Note, Part, Piece, Syllable

    part = Part(index=0, name="Voice", notes=[
        Note(midi=60, onset=0.0, duration=1.0, part=0, lyric="love",
             lyrics=(Syllable(number=1, text="love", syllabic="single"),)),
    ])
    piece = Piece(source_path="/tmp/x.musicxml", source_format="musicxml", parts=[part])
    out = base.extract_part(part, piece, groups_filter=["lyrics"])

    assert out["theme_love"] is None
    assert out["theme_love_divergence"] is None
    assert "no classifier is configured" in out["lyrics_classified_undefined_reason"]

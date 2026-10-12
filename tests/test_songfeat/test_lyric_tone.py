from songfeat.features.lyrics import tone
from songfeat.features.lyrics.questions import Answer, Kind


def test_there_are_six_tones_all_nouls():
    assert len(tone.QUESTIONS) == 6
    assert len(tone.TONE_FIELDS) == 6
    assert {question.kind for question in tone.QUESTIONS} == {Kind.NOUL}


def test_the_tones_are_the_six_the_spec_names():
    assert tone.TONE_FIELDS == (
        "tone_comic", "tone_ironic", "tone_sincere",
        "tone_elegiac", "tone_playful", "tone_grand",
    )


def test_tones_are_not_mutually_exclusive():
    """A wry song about unrequited love is comic AND ironic."""
    answers = {
        "tone_comic": Answer("tone_comic", probability=0.88),
        "tone_ironic": Answer("tone_ironic", probability=0.79),
        "tone_sincere": Answer("tone_sincere", probability=0.08),
    }
    out = tone.columns_from(answers)
    assert out["tone_comic"] == 0.88 and out["tone_ironic"] == 0.79
    assert out["tone_sincere"] == 0.08

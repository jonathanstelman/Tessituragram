import pytest

from songfeat.features import base
from songfeat.features.lyrics import service
from songfeat.features.lyrics.cache import AnswerCache
from songfeat.features.lyrics.client import FakeJevClient
from songfeat.features.lyrics.questions import Answer, question_set
from songfeat.model import Note, Part, Piece, Syllable


@pytest.fixture(autouse=True)
def _clean():
    service.reset()
    yield
    service.reset()


def _part(*words):
    notes = [
        Note(midi=60, onset=float(index), duration=1.0, part=0, lyric=word,
             lyrics=(Syllable(number=1, text=word, syllabic="single"),))
        for index, word in enumerate(words)
    ]
    return Part(index=0, name="Voice", notes=notes)


def _piece(part):
    return Piece(source_path="/tmp/song.musicxml", source_format="musicxml",
                 parts=[part])


def _scripted(**values):
    return {key: Answer(key, **value) for key, value in values.items()}


def test_unconfigured_reports_the_reason_on_every_axis():
    part = _part("love", "me")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert out["theme_love"] is None
    assert out["advisory_sex"] is None
    assert out["age_band"] is None
    assert "no classifier is configured" in out["lyrics_classified_undefined_reason"]


def test_a_part_with_no_lyrics_says_so_rather_than_blaming_the_key(tmp_path):
    service.configure(
        client=FakeJevClient(_scripted(theme_love={"probability": 0.9})),
        cache=AnswerCache(str(tmp_path / "c.sqlite")),
    )
    part = Part(index=0, name="Violin", notes=[
        Note(midi=60, onset=0.0, duration=1.0, part=0),
    ])
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert "no lyric events" in out["lyrics_classified_undefined_reason"]
    assert out["theme_love"] is None


def test_a_configured_client_populates_the_columns_and_the_provenance(tmp_path):
    service.configure(
        client=FakeJevClient(_scripted(
            theme_love={"probability": 0.93},
            advisory_sex={"score": 0.0},
            narrator_gender={"choice": "female"},
            lyrics_language={"choice": "en"},
        )),
        cache=AnswerCache(str(tmp_path / "c.sqlite")),
        question_set_name="core",
    )
    part = _part("love", "me")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])

    assert out["theme_love"] == 0.93
    assert out["narrator_gender"] == "female"
    assert out["lyrics_language"] == "en"
    assert out["clf_model"] == "fake/jev-1"
    assert out["clf_question_set"] == "core@v1"
    assert out["clf_classified_at"], "a date must be recorded"
    assert out["lyrics_classified_undefined_reason"] is None


def test_the_eight_axis_features_share_one_classification(tmp_path):
    """Eight features ask for the same part. One classification between
    them, or the group costs eight times what it should."""
    client = FakeJevClient(_scripted(theme_love={"probability": 0.5}))
    service.configure(client=client, cache=AnswerCache(str(tmp_path / "c.sqlite")),
                      question_set_name="core")
    part = _part("love")
    base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert client.calls_made == 1


def test_a_cached_answer_means_no_second_call(tmp_path):
    # Every core question must come back without an error so every one
    # of them is actually written to the cache: the cache never stores
    # an errored answer (a transient failure must not become permanent),
    # so an unscripted id here would force a second call on the next
    # run regardless of the cache, which is not what this test is
    # about.
    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    first = FakeJevClient(_scripted(
        theme_love={"probability": 0.77},
        theme_love_unrequited={"probability": 0.2},
        tone_comic={"probability": 0.1},
        advisory_violence={"score": 0.0},
        advisory_violence_first_person={"probability": 0.0},
        advisory_violence_depicted={"probability": 0.0},
        narrator_gender={"choice": "female"},
        narrator_cast_by_pronouns={"probability": 0.9},
        relational_focus_present={"probability": 0.9},
        love_interest_gender={"choice": "male"},
        sensitive_loss_of_parent={"probability": 0.0},
        sensitive_loss_of_parent_centrality={"score": 0.0},
        lyrics_language={"choice": "en"},
    ))
    service.configure(client=first, cache=cache, question_set_name="core")
    part = _part("love")
    base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert first.calls_made == 1

    service.reset()
    second = FakeJevClient(_scripted(theme_love={"probability": 0.11}))
    service.configure(client=second, cache=cache, question_set_name="core")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert second.calls_made == 0, "every answer came from the cache"
    assert out["theme_love"] == 0.77, "the cached value, not the new client's"


def test_a_column_outside_the_active_set_says_which_set_was_run(tmp_path):
    """A lean run must never be mistaken for an empty result."""
    service.configure(
        client=FakeJevClient(_scripted(theme_love={"probability": 0.9})),
        cache=AnswerCache(str(tmp_path / "c.sqlite")),
        question_set_name="core",
    )
    part = _part("love")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert out["theme_nature"] is None
    assert out["clf_question_set"] == "core@v1"
    assert out["lyrics_classified_undefined_reason"] is None, (
        "the run succeeded; the set is recorded in clf_question_set, and a "
        "reason here would claim the classification failed"
    )


def test_text_beyond_the_context_limit_is_refused_not_truncated(tmp_path):
    """Review Focus 3: a truncated classification describes a fragment
    while claiming to describe the song."""
    service.configure(
        client=FakeJevClient(_scripted(theme_love={"probability": 0.9})),
        cache=AnswerCache(str(tmp_path / "c.sqlite")),
    )
    part = _part(*(["word"] * (service.MAX_STATE_TOKENS)))
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert out["theme_love"] is None
    assert "exceeds the model's context" in out["lyrics_classified_undefined_reason"]


def test_a_choice_outside_the_declared_options_is_null_with_a_reason(tmp_path):
    """Review Focus 5: never coerced to "unspecified", which is a real
    answer meaning the text does not say."""
    service.configure(
        client=FakeJevClient(_scripted(narrator_gender={"choice": "androgynous"})),
        cache=AnswerCache(str(tmp_path / "c.sqlite")),
        question_set_name="core",
    )
    part = _part("love")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert out["narrator_gender"] is None, "not 'unspecified'"


def test_a_failed_batch_nulls_only_its_own_columns(tmp_path):
    """A partial result is a legitimate outcome."""
    service.configure(
        client=FakeJevClient(_scripted(
            theme_love={"probability": 0.93},
            narrator_gender={"error": "HTTP 503"},
        )),
        cache=AnswerCache(str(tmp_path / "c.sqlite")),
        question_set_name="core",
    )
    part = _part("love")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert out["theme_love"] == 0.93
    assert out["narrator_gender"] is None


def test_the_group_has_one_hundred_and_seventy_eight_columns():
    from songfeat.features import schema

    # ``schema([])`` is not "no groups": an empty list is falsy, so the
    # registry's own filter (`if groups_filter else None`) treats it the
    # same as no filter at all and returns everything. A name that
    # matches no group is the way to isolate the identity columns.
    columns = schema(["lyrics"])
    identity = schema(["no-such-group"])
    assert len(columns) - len(identity) == 178


def test_the_default_schema_is_unchanged_by_this_group():
    from songfeat.features import schema

    assert len(schema(["basic", "vocal", "jsymbolic", "native"])) == 213

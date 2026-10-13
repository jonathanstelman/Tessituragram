import pytest

from songfeat.features import base
from songfeat.features.lyrics import service
from songfeat.features.lyrics.cache import AnswerCache
from songfeat.features.lyrics.client import FakeJevClient, MISSING_KEY
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


def test_lyrics_present_but_empty_after_reassembly_names_the_count(tmp_path):
    """Fix round 1, Finding 1 (CRITICAL): a whitespace-only syllable
    passes assemble_text's own "no lyrics at all" check -- a space is a
    non-empty string -- so without this check the classifier would be
    called with an empty state and report confident values for a song
    with nothing in it."""
    service.configure(
        client=FakeJevClient(_scripted(theme_love={"probability": 0.9})),
        cache=AnswerCache(str(tmp_path / "c.sqlite")),
    )
    part = _part(" ")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert out["theme_love"] is None
    reason = out["lyrics_classified_undefined_reason"]
    assert reason is not None
    assert "0 word(s)" in reason
    assert reason != service.NO_LYRICS, (
        "distinct from 'no lyric events in the source': a lyric event "
        "was present, it just reassembled to nothing"
    )


def test_an_unavailable_reason_overrides_the_generic_not_configured_message(tmp_path):
    """Fix round 1, Finding 2: the CLI knows the difference between "no
    JEV_KEY" and "nobody requested this group"; the service must report
    whichever one the caller actually hands it."""
    service.configure(client=None, unavailable_reason=MISSING_KEY)
    part = _part("love")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert out["lyrics_classified_undefined_reason"] == MISSING_KEY


def test_without_an_unavailable_reason_the_generic_message_still_applies():
    """The default run, where the group was never requested at all,
    keeps reporting NOT_CONFIGURED -- that distinction is the point of
    Finding 2's fix."""
    service.reset()
    part = _part("love")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert out["lyrics_classified_undefined_reason"] == service.NOT_CONFIGURED


def test_classified_at_comes_from_the_cache_entry_not_the_run(tmp_path):
    """Fix round 1, Finding 5: a cache hit must report when the song was
    actually classified, never today's date. Seeds a cache entry dated
    plainly not-today and pins that exact string on the way out -- every
    other test in this file populates and reads the cache on the same
    day, which would pass even if ``classified_at`` came from the run's
    own clock."""
    from songfeat.features.lyrics.assemble import assemble_text

    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    part = _part("love")
    assembled = assemble_text(part)
    question = next(q for q in question_set("core") if q.id == "theme_love")
    cache.put(assembled.sha256, "fake/jev-1", question,
              Answer("theme_love", probability=0.42), "2020-01-01")

    service.configure(
        client=FakeJevClient(_scripted(theme_love={"probability": 0.99})),
        cache=cache, question_set_name="core",
    )
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert out["theme_love"] == 0.42, "the cached value, not the fresh one"
    assert out["clf_classified_at"] == "2020-01-01"


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


# --- failure inside classify_part (fix wave, C1) ---------------------------


class _RaisingClient:
    """A client that fails, counting how often it was asked to."""

    model = "fake/jev-1"
    resolved_model = None

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls_made = 0
        self.asks = 0

    def ask(self, state, questions):
        self.asks += 1
        raise self.error


def test_a_raising_client_is_asked_once_per_song_not_once_per_axis(tmp_path):
    """The memo used to be written only on success, so each of the eight
    axis features re-entered classify_part and re-attempted the call:
    one part cost 7 further ``ask`` invocations -- up to 56 HTTP calls
    for one song on a full run, repeated per file -- and every one of
    them was paid for."""
    client = _RaisingClient(RuntimeError("the roof fell in"))
    service.configure(client=client,
                      cache=AnswerCache(str(tmp_path / "c.sqlite")))
    part = _part("love", "me")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])

    assert client.asks == 1, "one attempt per song, not one per axis"
    reason = out["lyrics_classified_undefined_reason"]
    assert reason is not None, "a null group with a null reason is the defect"
    assert "RuntimeError: the roof fell in" in reason
    # The group nulls, as a whole-group failure must.
    assert out["theme_love"] is None
    assert out["advisory_sex"] is None
    assert out["age_band"] is None
    assert out["age_band_rule"] is None


def test_the_failure_reason_never_carries_the_api_key(tmp_path, monkeypatch):
    """The reason is a user-visible column. The key is read once from the
    environment and goes in a header -- but this reason is built from an
    exception raised by code we do not own, and a key that reached a CSV
    could not be un-leaked."""
    monkeypatch.setenv("JEV_KEY", "sk-live-NOTAREALKEY-7788")
    client = _RaisingClient(
        RuntimeError("401 while authenticating with sk-live-NOTAREALKEY-7788")
    )
    service.configure(client=client,
                      cache=AnswerCache(str(tmp_path / "c.sqlite")))
    part = _part("love", "me")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])

    reason = out["lyrics_classified_undefined_reason"]
    assert "sk-live-NOTAREALKEY-7788" not in reason
    assert "[redacted]" in reason
    assert "401 while authenticating with" in reason, (
        "redaction must not cost the reason its meaning"
    )


class _OneBatchThenBudget:
    """Answers the first batch, then stops on budget -- carrying what it
    already answered, because those answers were paid for."""

    model = "fake/jev-1"
    resolved_model = None

    def __init__(self, answered: int) -> None:
        self.answered = answered
        self.calls_made = 1
        self.asks = 0

    def ask(self, state, questions):
        from songfeat.features.lyrics.client import BudgetExceeded

        self.asks += 1
        paid_for = [
            Answer(question.id, probability=0.75)
            for question in questions[: self.answered]
        ]
        raise BudgetExceeded("stopping after 1 calls", answers=paid_for)


def test_answers_paid_for_before_a_budget_stop_reach_the_cache(tmp_path):
    """3 calls made, 60 questions answered, BudgetExceeded on the fourth,
    and ``ask`` discarded the accumulated answers on the way out:
    nothing reached the cache, so the next run paid for them again."""
    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    client = _OneBatchThenBudget(answered=20)
    service.configure(client=client, cache=cache, question_set_name="full")
    part = _part("love", "me")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])

    assert client.asks == 1
    assert "BudgetExceeded" in out["lyrics_classified_undefined_reason"]

    asked = question_set("full")
    banked = sum(
        1 for question in asked
        if cache.get(part_hash(part), "fake/jev-1", question) is not None
    )
    assert banked == 20, (
        "every answer the budget stop had already been billed for must be "
        "in the cache, and nothing else"
    )


def part_hash(part):
    from songfeat.features.lyrics.assemble import assemble_text

    return assemble_text(part).sha256


class _StrayIdClient:
    model = "fake/jev-1"
    resolved_model = "fake/jev-1.0.1"
    calls_made = 0

    def ask(self, state, questions):
        answers = [
            Answer(question.id, probability=0.8, score=4.0, choice="en")
            for question in questions
            if question.id != "theme_love"          # one question omitted
        ]
        answers.append(Answer("a_question_nobody_asked", probability=0.1))
        return answers


def test_an_unknown_or_missing_question_id_nulls_one_column_not_the_group(tmp_path):
    """A client returning an id we never asked about used to raise
    KeyError inside classify_part, which -- before C1 -- nulled all 178
    columns with no reason at all. An omitted id did the same."""
    service.configure(client=_StrayIdClient(),
                      cache=AnswerCache(str(tmp_path / "c.sqlite")),
                      question_set_name="core")
    part = _part("love", "me")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])

    assert out["lyrics_classified_undefined_reason"] is None, (
        "one stray answer is not a whole-group failure"
    )
    # The omitted question's own column nulls...
    assert out["theme_love"] is None
    # ... and its reason is reported rather than dropped.
    assert "theme_love: the classifier returned no answer" in \
        out["_errors"]["lyrics_themes"]
    # ... while everything else keeps its value.
    assert out["tone_comic"] == 0.8
    assert out["advisory_violence"] == 4.0


def test_an_errored_answer_reports_its_status_rather_than_a_bare_null(tmp_path):
    """``Answer.error`` carries "HTTP 503", "no score returned", "answer
    'androgynous' is not a declared option" -- and every axis used to map
    it to a bare None and drop the error, so the spec's requirement that
    a failure's reason carry the status reached nothing."""
    service.configure(
        client=FakeJevClient({
            "advisory_violence": Answer("advisory_violence", error="HTTP 503"),
            "advisory_violence_depicted": Answer(
                "advisory_violence_depicted", probability=0.4),
        }),
        cache=AnswerCache(str(tmp_path / "c.sqlite")),
        question_set_name="core",
    )
    part = _part("love", "me")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])

    assert out["advisory_violence"] is None
    summary = out["_errors"]["lyrics_advisories"]
    assert "advisory_violence: HTTP 503" in summary
    # Exactly the one dimension this axis asked about in the core set,
    # and the two modifiers -- one of which answered. So two failures:
    # the intensity (503) and the first_person modifier (unscripted).
    assert summary.startswith("2 question(s) failed: "), summary
    assert out["advisory_violence_depicted"] == 0.4


def test_the_resolved_model_is_what_provenance_records(tmp_path):
    """``clf_model`` recorded "jev-latest", an alias that resolves
    server-side. Provenance cannot distinguish databases built against
    different model versions if it records the alias, which is the
    column's entire stated purpose."""
    service.configure(
        client=FakeJevClient(_scripted(theme_love={"probability": 0.9}),
                             model="jev-latest",
                             resolved_model="jev-1.13.0"),
        cache=AnswerCache(str(tmp_path / "c.sqlite")),
        question_set_name="core",
    )
    part = _part("love", "me")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert out["clf_model"] == "jev-1.13.0"


def test_without_a_resolved_id_provenance_falls_back_to_the_alias(tmp_path):
    service.configure(
        client=FakeJevClient(_scripted(theme_love={"probability": 0.9}),
                             model="jev-latest"),
        cache=AnswerCache(str(tmp_path / "c.sqlite")),
        question_set_name="core",
    )
    part = _part("love", "me")
    out = base.extract_part(part, _piece(part), groups_filter=["lyrics"])
    assert out["clf_model"] == "jev-latest"

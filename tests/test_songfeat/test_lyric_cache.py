import os
import sqlite3

from songfeat.features.lyrics.cache import AnswerCache, SCHEMA_VERSION
from songfeat.features.lyrics.questions import Answer, Kind, Question, question_set

QUESTION = Question(id="theme_love", kind=Kind.NOUL, text="Is this about love?",
                    column="theme_love", axis="themes")


def test_a_miss_returns_none(tmp_path):
    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    assert cache.get("abc", "typesafe/jev-1.13", QUESTION) is None


def test_a_round_trip_returns_the_answer_and_its_original_date(tmp_path):
    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    cache.put("abc", "typesafe/jev-1.13", QUESTION,
              Answer("theme_love", probability=0.91, confidence=0.8),
              "2026-10-12")
    answer, when = cache.get("abc", "typesafe/jev-1.13", QUESTION)
    assert answer.probability == 0.91
    assert answer.confidence == 0.8
    assert when == "2026-10-12", "the classification's date, not today's"


def test_rewording_a_question_invalidates_only_that_question(tmp_path):
    """This is why the key is per question. A per-set key would discard
    every answer on every wording change, which is the moment the cache
    is most needed."""
    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    other = Question(id="theme_nature", kind=Kind.NOUL, text="Is this about nature?",
                     column="theme_nature", axis="themes")
    cache.put("abc", "typesafe/jev-1.13", QUESTION, Answer("theme_love", probability=0.9), "2026-10-12")
    cache.put("abc", "typesafe/jev-1.13", other, Answer("theme_nature", probability=0.1), "2026-10-12")

    reworded = Question(id="theme_love", kind=Kind.NOUL,
                        text="Does this text concern love?",
                        column="theme_love", axis="themes")
    assert cache.get("abc", "typesafe/jev-1.13", reworded) is None
    assert cache.get("abc", "typesafe/jev-1.13", other) is not None


def test_a_different_model_is_a_different_entry(tmp_path):
    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    cache.put("abc", "typesafe/jev-1.13", QUESTION, Answer("theme_love", probability=0.9), "2026-10-12")
    assert cache.get("abc", "typesafe/jev-1.14", QUESTION) is None


def test_a_corrupt_cache_file_degrades_to_a_miss(tmp_path):
    """Review Focus 4: a bad cache must not take the run down with it."""
    path = tmp_path / "c.sqlite"
    path.write_bytes(b"this is not a database")
    cache = AnswerCache(str(path))
    assert cache.get("abc", "typesafe/jev-1.13", QUESTION) is None
    cache.put("abc", "typesafe/jev-1.13", QUESTION, Answer("theme_love", probability=0.9), "2026-10-12")


def test_an_older_schema_version_is_discarded_rather_than_read(tmp_path):
    """Review Focus 4: an answer stored under an older layout may mean
    something different. Treat the whole file as a miss."""
    path = tmp_path / "c.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    connection.execute("INSERT INTO meta VALUES ('schema_version', '0')")
    connection.commit()
    connection.close()

    cache = AnswerCache(str(path))
    assert cache.get("abc", "typesafe/jev-1.13", QUESTION) is None
    cache.put("abc", "typesafe/jev-1.13", QUESTION, Answer("theme_love", probability=0.7), "2026-10-12")
    answer, _when = cache.get("abc", "typesafe/jev-1.13", QUESTION)
    assert answer.probability == 0.7, "recreated at the current version and usable"


def test_an_errored_answer_is_not_cached(tmp_path):
    """A timeout is not a judgment about the song; caching it would make
    a transient failure permanent."""
    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    cache.put("abc", "typesafe/jev-1.13", QUESTION,
              Answer("theme_love", error="timeout"), "2026-10-12")
    assert cache.get("abc", "typesafe/jev-1.13", QUESTION) is None


def test_the_schema_version_is_pinned():
    assert SCHEMA_VERSION == 1


def test_a_locked_database_degrades_to_a_miss(tmp_path):
    """Review Focus 4: another process holding the write lock must not
    crash the run either."""
    path = tmp_path / "c.sqlite"
    # Create the cache once so the schema exists, then hold an exclusive
    # lock with a second raw connection before a second AnswerCache
    # tries to use the same file.
    AnswerCache(str(path)).close()
    blocker = sqlite3.connect(str(path))
    blocker.execute("BEGIN EXCLUSIVE")

    cache = AnswerCache(str(path))
    assert cache.get("abc", "typesafe/jev-1.13", QUESTION) is None
    # Must not raise even though the write cannot land while locked.
    cache.put("abc", "typesafe/jev-1.13", QUESTION, Answer("theme_love", probability=0.9), "2026-10-12")

    blocker.execute("ROLLBACK")
    blocker.close()


def test_a_zero_probability_round_trips_as_zero_not_none(tmp_path):
    """0.0 is a real answer. A cache that coerces it to None would make
    a miss indistinguishable from a confident zero."""
    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    cache.put("abc", "typesafe/jev-1.13", QUESTION,
              Answer("theme_love", probability=0.0, confidence=0.0), "2026-10-12")
    answer, _when = cache.get("abc", "typesafe/jev-1.13", QUESTION)
    assert answer.probability == 0.0
    assert answer.probability is not None
    assert answer.confidence == 0.0
    assert answer.confidence is not None


def test_changed_criteria_invalidates_only_that_question(tmp_path):
    """Fix round 1, finding 1: the key must cover the resolved criteria
    too, not just question.text. A Score question's criteria normally
    come from the shared SCORE_LEVELS default, which a question-level
    ``criteria`` override replaces -- this is the same wording-change
    hazard as the reworded-text test, but for the part of a question
    the model sees that text.hash alone does not cover."""
    score_question = Question(id="advisory_violence", kind=Kind.SCORE, levels=6,
                              text="How much violence?", column="advisory_violence",
                              axis="advisories")
    other = Question(id="theme_nature", kind=Kind.NOUL, text="Is this about nature?",
                     column="theme_nature", axis="themes")
    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    cache.put("abc", "typesafe/jev-1.13", score_question,
              Answer("advisory_violence", score=2.0), "2026-10-12")
    cache.put("abc", "typesafe/jev-1.13", other,
              Answer("theme_nature", probability=0.1), "2026-10-12")

    # Same id, same kind, same text -- but a per-question criteria
    # override now replaces the shared SCORE_LEVELS rubric. The answer
    # above was computed against a scale this question no longer uses.
    rescaled = Question(id="advisory_violence", kind=Kind.SCORE, levels=6,
                        text="How much violence?", column="advisory_violence",
                        axis="advisories",
                        criteria=("none", "mild", "moderate", "severe", "extreme", "graphic"))
    assert cache.get("abc", "typesafe/jev-1.13", rescaled) is None
    assert cache.get("abc", "typesafe/jev-1.13", other) is not None


def test_put_many_batches_several_answers_under_one_commit(tmp_path):
    """put_many must store a whole batch's good answers -- retrievable
    individually by get() under the shared classified_at -- and must not
    cache an errored answer in that same batch, same as put()."""
    other = Question(id="theme_nature", kind=Kind.NOUL, text="Is this about nature?",
                     column="theme_nature", axis="themes")
    failed = Question(id="tone_comic", kind=Kind.NOUL, text="Is this comic?",
                      column="tone_comic", axis="tone")
    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    pairs = [
        (QUESTION, Answer("theme_love", probability=0.91, confidence=0.8)),
        (other, Answer("theme_nature", probability=0.2, confidence=0.6)),
        (failed, Answer("tone_comic", error="timeout")),
    ]
    cache.put_many("abc", "typesafe/jev-1.13", pairs, "2026-10-12")

    love_answer, love_when = cache.get("abc", "typesafe/jev-1.13", QUESTION)
    assert love_answer.probability == 0.91
    assert love_answer.confidence == 0.8
    assert love_when == "2026-10-12"

    nature_answer, nature_when = cache.get("abc", "typesafe/jev-1.13", other)
    assert nature_answer.probability == 0.2
    assert nature_answer.confidence == 0.6
    assert nature_when == "2026-10-12"

    assert cache.get("abc", "typesafe/jev-1.13", failed) is None

    stored = cache._connection.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
    assert stored == 2, "only the two non-errored answers are stored"


def test_a_core_run_then_a_full_run_reuses_the_cores_answers(tmp_path):
    """The key is per question, not per set: a lean 'core' run's answers
    must be reusable, unchanged, by a later 'full' run that asks more
    questions of the same text under the same model."""
    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    core_questions = [
        Question(id="theme_love", kind=Kind.NOUL, text="Is this about love?",
                 column="theme_love", axis="themes"),
        Question(id="theme_nature", kind=Kind.NOUL, text="Is this about nature?",
                 column="theme_nature", axis="themes"),
    ]
    full_questions = core_questions + [
        Question(id="tone_comic", kind=Kind.NOUL, text="Is this comic?",
                 column="tone_comic", axis="tone"),
    ]

    for question in core_questions:
        cache.put("abc", "typesafe/jev-1.13", question,
                  Answer(question.id, probability=0.5), "2026-10-12")

    hits = []
    misses = []
    for question in full_questions:
        result = cache.get("abc", "typesafe/jev-1.13", question)
        if result is None:
            misses.append(question.id)
        else:
            hits.append(question.id)

    assert hits == ["theme_love", "theme_nature"]
    assert misses == ["tone_comic"]


def test_tests_never_see_the_real_default_cache_path():
    """The autouse guard in conftest redirects cache.DEFAULT_PATH into
    tmp_path. Without it, any code path that falls back to the default
    -- ``--validate-lyrics`` has no cache flag of its own -- writes a
    real, mutable cache into the repository root, which is where a 20KB
    one was found."""
    from songfeat.features.lyrics import cache as cache_module

    assert cache_module.DEFAULT_PATH.endswith(
        os.path.join(".songfeat", "jev-cache.sqlite")
    )
    assert cache_module.DEFAULT_PATH != os.path.join(".songfeat", "jev-cache.sqlite"), (
        "the default path must be redirected under tmp_path during tests"
    )
    assert os.path.isabs(cache_module.DEFAULT_PATH)


def test_a_rolled_forward_alias_discards_what_was_stored_under_it(tmp_path):
    """The cache keys on the alias we ask with ("jev-latest"), because a
    lookup happens before any call and the resolved id is unknown then.
    So when the server rolls the alias forward, the old version's
    answers would be served for ever against a different model. Seeing a
    different resolved id for a known alias is the proof that happened.
    """
    cache = AnswerCache(str(tmp_path / "c.sqlite"))
    question = question_set("core")[0]
    cache.put("hash", "jev-latest", question,
              Answer(question.id, probability=0.25), "2026-01-01")

    first = cache.note_resolved_model("jev-latest", "jev-1.13.0")
    assert first is False, "a first sighting is not a change"
    hit = cache.get("hash", "jev-latest", question)
    assert hit is not None and hit[0].probability == 0.25

    rolled = cache.note_resolved_model("jev-latest", "jev-1.14.0")
    assert rolled is True, "a new resolved id for a known alias is a roll-forward"
    assert cache.get("hash", "jev-latest", question) is None, (
        "answers written against the previous model version must not be "
        "served against the new one"
    )
    # Still a change the second time only if it changes again.
    assert cache.note_resolved_model("jev-latest", "jev-1.14.0") is False

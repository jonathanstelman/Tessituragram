import sqlite3

import pytest

from songfeat.features.lyrics.cache import AnswerCache, SCHEMA_VERSION
from songfeat.features.lyrics.questions import Answer, Kind, Question

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

"""A per-question answer cache, so a run costs money once.

Keyed on (text hash, model, question id, question text hash) -- per
QUESTION, never per question set. That is what makes the lean question
set free: a core run's answers are reusable by a later full run, and
rewording one question costs one column rather than a whole song.

The cache, not the model, is what makes re-runs reproducible: Jev's
probabilities are not guaranteed bit-identical between calls. A
consequence worth knowing is that two databases built from the same
scores at different times may differ slightly if either was built cache
cold -- which is what the provenance columns make visible.

Every failure here degrades to a miss. A cache that cannot be read is an
inconvenience; a cache that takes the run down, or serves an answer
stored under a different question, is a defect.
"""

from __future__ import annotations

import json
import os
import sqlite3

from .assemble import text_sha256
from .questions import Answer, Question

SCHEMA_VERSION = 1
DEFAULT_PATH = os.path.join(".songfeat", "jev-cache.sqlite")

_DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS answers (
    text_hash     TEXT NOT NULL,
    model         TEXT NOT NULL,
    question_id   TEXT NOT NULL,
    question_hash TEXT NOT NULL,
    payload       TEXT NOT NULL,
    classified_at TEXT NOT NULL,
    PRIMARY KEY (text_hash, model, question_id, question_hash)
);
"""


def question_hash(question: Question) -> str:
    """The question text's hash -- reuses the lyric text hasher, since
    both are "sha256 of this exact string" and must agree on encoding."""
    return text_sha256(question.text)


class AnswerCache:
    """A sqlite-backed cache of classifier answers, keyed per question.

    Any fault opening or using the backing file -- a corrupt or
    non-sqlite file, another process holding the write lock, or a
    stored schema version that does not match this code's -- degrades
    to running without a cache rather than raising. A version mismatch
    discards the old file outright: an answer recorded under a
    different table shape might mean something else entirely, so it is
    never partially trusted.
    """

    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path
        self._connection: sqlite3.Connection | None = None
        self._open()

    def _open(self) -> None:
        try:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            connection = sqlite3.connect(self.path)
            version = self._version(connection)
            if version is not None and version != SCHEMA_VERSION:
                # An answer stored under an older layout may mean
                # something different. Discard rather than guess.
                connection.close()
                os.replace(self.path, self.path + f".v{version}.bak")
                connection = sqlite3.connect(self.path)
            connection.executescript(_DDL)
            connection.execute(
                "INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            connection.commit()
            self._connection = connection
        except (sqlite3.Error, OSError):
            # Corrupt, locked, or unwritable: run without a cache.
            self._connection = None

    @staticmethod
    def _version(connection: sqlite3.Connection) -> int | None:
        try:
            row = connection.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
        except sqlite3.Error:
            return None
        return int(row[0]) if row else None

    def get(
        self, text_hash: str, model: str, question: Question
    ) -> tuple[Answer, str] | None:
        """The cached answer and its original ``classified_at``, or
        ``None`` on a miss -- including a miss caused by a cache fault,
        which is indistinguishable from an ordinary miss by design."""
        if self._connection is None:
            return None
        try:
            row = self._connection.execute(
                "SELECT payload, classified_at FROM answers WHERE "
                "text_hash=? AND model=? AND question_id=? AND question_hash=?",
                (text_hash, model, question.id, question_hash(question)),
            ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        return Answer(**json.loads(row[0])), row[1]

    def put(
        self, text_hash: str, model: str, question: Question,
        answer: Answer, classified_at: str,
    ) -> None:
        """Store one question's answer. An errored answer (a timeout or
        similar) is never stored: caching it would make a transient
        failure permanent."""
        if answer.error is not None or self._connection is None:
            return
        try:
            self._connection.execute(
                "INSERT OR REPLACE INTO answers VALUES (?, ?, ?, ?, ?, ?)",
                (text_hash, model, question.id, question_hash(question),
                 json.dumps(answer.__dict__), classified_at),
            )
            self._connection.commit()
        except sqlite3.Error:
            return

    def put_many(self, text_hash, model, pairs, classified_at) -> None:
        """Store several (question, answer) pairs under one classification
        timestamp, e.g. the results of one batched call to the classifier."""
        for question, answer in pairs:
            self.put(text_hash, model, question, answer, classified_at)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

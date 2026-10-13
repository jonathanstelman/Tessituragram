"""Reassemble a score's lyrics into text.

MusicXML stores one ``<lyric>`` per note per verse, so "Erlkönig" is four
notes carrying "Er", "l", "kö", "nig" with syllabic markers that say how
to put them back together. Everything here is deterministic: no model,
no network, no configuration.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass

from ...model import Part

#: Syllabic markers that continue the previous syllable rather than
#: starting a new word. MusicXML's vocabulary is begin/middle/end/single.
_CONTINUING = frozenset({"middle", "end"})


@dataclass(frozen=True)
class LyricText:
    text: str
    word_count: int
    verse_count: int
    sha256: str


def normalise(text: str) -> str:
    """NFC, LF endings, no trailing blanks, exactly one final newline.

    Pinned by test because the cache key is a hash of this output: a
    platform-dependent normalisation would silently halve the hit rate.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def text_sha256(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def assemble_text(part: Part) -> LyricText | None:
    """Join this part's syllables into one line per verse.

    Returns ``None`` -- never an empty ``LyricText`` -- when the part
    carries no lyrics at all. An empty result would read as "we read
    this song and found no words", which is a different claim.
    """
    verses: dict[int, list[str]] = {}
    for note in sorted(part.notes, key=lambda n: (n.onset, n.midi)):
        for syllable in note.lyrics:
            if not syllable.text:
                continue
            words = verses.setdefault(syllable.number, [])
            if words and syllable.syllabic in _CONTINUING:
                words[-1] += syllable.text
            else:
                words.append(syllable.text)

    if not verses:
        return None

    # Verse numbers are whatever the file carried: a score may start at
    # 2, or skip 3. Sort what is there; never fill a gap.
    lines = [" ".join(verses[number]) for number in sorted(verses)]
    text = normalise("\n".join(lines))
    return LyricText(
        text=text,
        # A syllable of pure whitespace (e.g. a stray space character)
        # survives the ``not syllable.text`` guard above -- it is a
        # non-empty string -- so it reaches ``verses`` and must not be
        # counted as a word. Fix round 1: this was silently reporting
        # word_count=1 for a part whose only "lyric" was blank.
        word_count=sum(
            1 for words in verses.values() for word in words if word.strip()
        ),
        verse_count=len(verses),
        sha256=text_sha256(text),
    )

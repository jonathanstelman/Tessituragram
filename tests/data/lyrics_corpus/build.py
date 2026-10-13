"""Generate the corpus's MusicXML from songs.py.

Hand-writing 36 MusicXML files is error-prone and unreviewable; this
makes the text the source of truth and the XML a build artifact. The
artifacts are still committed, so a test run needs no generation step.

The committed files must be byte-stable, or every later run looks like a
change. Two things in music21's output are not: the ``<encoding-date>``
it stamps with today's date, and the part id, which music21 builds from
a fresh MD5 whenever a part has no explicitly identified instrument
(``Instrument.partIdRandomize``) and so differs on every run. The date
line is dropped and the random id is rewritten to ``P1``; there is one
part per score, so nothing is made ambiguous by fixing it.

Run: venv/bin/python tests/data/lyrics_corpus/build.py
"""

from __future__ import annotations

import pathlib
import re

from music21 import metadata, note, stream
from music21.musicxml import m21ToXml

from songs import SONGS

HERE = pathlib.Path(__file__).parent

#: music21 stamps the day the file was written into the header.
_ENCODING_DATE = re.compile(r"[ \t]*<encoding-date>[^<]*</encoding-date>\r?\n")

#: ``P`` followed by a fresh MD5, as ``partIdRandomize`` writes it.
_RANDOM_PART_ID = re.compile(r"P[0-9a-f]{32}")


def build(song) -> stream.Score:
    part = stream.Part()
    longest = max(len(verse) for verse in song.verses)
    for index in range(longest):
        element = note.Note("C4", quarterLength=1.0)
        for number, verse in enumerate(song.verses, start=1):
            if index >= len(verse):
                continue
            word = verse[index]
            text = word.replace("-", "")
            if word.endswith("-"):
                syllabic = "begin"
            elif index and verse[index - 1].endswith("-"):
                syllabic = "end"
            else:
                syllabic = "single"
            element.addLyric(text, applyRaw=True)
            element.lyrics[-1].number = number
            element.lyrics[-1].syllabic = syllabic
        part.append(element)
    score = stream.Score([part])
    score.insert(0, metadata.Metadata(title=song.title))
    return score


def serialise(song) -> str:
    xml = m21ToXml.GeneralObjectExporter().parse(build(song)).decode("utf-8")
    xml = _RANDOM_PART_ID.sub("P1", _ENCODING_DATE.sub("", xml))
    # music21 ends the document without a newline; add one so the
    # committed files are ordinary POSIX text files.
    return xml if xml.endswith("\n") else xml + "\n"


if __name__ == "__main__":
    for song in SONGS:
        path = HERE / f"{song.slug}.musicxml"
        path.write_text(serialise(song), encoding="utf-8", newline="\n")
        print(song.slug)

# songfeat

**Turn a folder of sheet music into a spreadsheet you can sort and filter.**

Point `songfeat` at your scores and it reads each one, measures the singing in it, and writes a
row per vocal part: how high and low it goes, where it sits most of the time, how much it leaps,
how long the phrases run, how hard it works the voice — and, if you ask it to, what the words
are about.

It is built for choosing repertoire. The question it is meant to answer is not "is this a good
song" but "which of my 400 songs fit *this* student" — and, just as often, which ones to rule
out.

```
songfeat ~/Music/arias -o library.csv
```

That writes one row per vocal part, 213 columns wide. Everything in it is computed from the
file itself: offline, free, and the same every time you run it.

---

## Contents

- [What you need](#what-you-need)
- [Running it](#running-it)
- [What the columns tell you](#what-the-columns-tell-you)
- [Reading the words: the lyrics group](#reading-the-words-the-lyrics-group)
- [What these numbers do *not* mean](#what-these-numbers-do-not-mean)
- [Output formats](#output-formats)
- [Checking the tool against itself](#checking-the-tool-against-itself)
- [Known limits](#known-limits)

---

## What you need

Scores in **MusicXML** (`.musicxml`, `.xml`, `.mxl`) or **MIDI** (`.mid`, `.midi`).

MusicXML is much better. MIDI carries the notes but usually not the words, so on MIDI files
every lyric column comes back blank — correctly blank, with a reason saying why, rather than
quietly reading as zero.

If your scores come from the Tessituragram corpus, every file ends with a stray low C that is a
parsing marker rather than music. It will wreck your pitch ranges. Strip it:

```
songfeat ~/Music/arias --drop-trailing-marker -o library.csv
```

---

## Running it

```
songfeat <files or folders> [-o output] [--groups ...] [options]
```

| What you want | Command |
|---|---|
| Everything analytic, to a spreadsheet | `songfeat scores/ -o library.csv` |
| Just one folder, no subfolders | `songfeat scores/ --no-recursive -o library.csv` |
| See the column names before you run | `songfeat --schema` |
| See what every column means | `songfeat --list-features` |
| Only the vocal measurements | `songfeat scores/ --groups vocal -o library.csv` |
| Add the lyric reading (needs a key) | `songfeat scores/ --groups basic,vocal,jsymbolic,native,lyrics -o library.csv` |
| Find columns that are useless on *your* library | `songfeat scores/ --profile` |

A plain run gives you the four analytic groups and 213 columns. The lyrics group is the one
thing you have to ask for by name, because it is the one thing that is neither offline nor free.

---

## What the columns tell you

Every row starts with ten **identity** columns — which file, which part, what the part was
called, and whether `songfeat` thinks it is a singing part at all (`is_vocal_candidate`,
`vocal_confidence`, and the four signals behind that guess: lyrics, monophony, range, naming).
A piano reduction and a vocal line both get rows; the identity columns are how you tell them
apart.

Then four analytic groups, always computed:

### `basic` — 38 columns

The things you would read off the first page. Key as notated and key as the notes actually
imply, time signature and how often it changes, tempo and how much it moves, how much music
there is, and whether the score carries sung text at all.

### `vocal` — 75 columns

The heart of it, and the part written for singing teachers specifically.

| Feature | What it tells you |
|---|---|
| **tessitura** | the pitch quartiles — where the line actually lives, not just its extremes |
| **pitch_range** | lowest and highest sounding notes |
| **passaggi** | how long the line dwells in each of the nine passaggio zones, for high, medium and low voice — plus how often it crosses them and the longest unbroken span in each |
| **leaps** | leap size, how often, which direction, how they are prepared, and whether a leap crosses a passaggio |
| **runs** | fast stepwise passages: how many, how long, how much of the line they take up |
| **text_setting** | syllable count and melisma — how many notes each syllable carries |
| **vocal_load** | phonatory load: total vocal-fold vibrations (cycle dose), time spent sounding, time resting, and sustained-note burden |
| **phrasing** | rest-delimited segments — **read the warning below before using these** |
| **chromaticism** | how far the line departs from the prevailing key |

**tessitura is emitted twice** — once weighted by how long each note sounds, once by how many
notes there are. That is not indecision. The reference spreadsheet and the reference
implementation disagree about which one *is* tessitura, so both are reported and labelled rather
than one being silently picked.

### `jsymbolic` — 69 columns · `native` — 21 columns

Standard musicology measurements, computed through `music21`: melodic interval statistics,
rhythmic pulse strength, register importance, chord-quality prevalence, tonal certainty. Useful
for clustering and similarity work. If you are choosing repertoire for a student, you will
mostly ignore these — they are there so the data is comparable with other research.

---

## Reading the words: the lyrics group

**178 columns, opt-in, and the only part that costs money.** It reads the lyrics out of a
MusicXML file and asks a classification model (Jev, from TypeSafe) 153 typed questions about
them.

### Setting it up

1. Get a key from TypeSafe.
2. Put it in a file called `.env` in the project root: `JEV_KEY=your-key-here`
3. Ask for the group by name: `--groups basic,vocal,jsymbolic,native,lyrics`

Without the key, everything else in the tool works exactly as before and every lyric column
comes back blank with "no JEV_KEY is set" as the reason. The key is read from the environment
only — never from the command line, where it would end up in your shell history.

**Cost: under three cents per hundred songs.** A 37-song corpus costs about half a cent.

### What it tells you

| Axis | Columns | What it is |
|---|---|---|
| **themes** | 74 | what the song is about — 9 families (Love, Relationships, Nature, Living, Resilience & Self, Religion & Transcendence, Social Commentaries, Activities & Craft, Mythology & Folklore) and 56 more specific subjects beneath them |
| **tone** | 6 | how it treats its subject: comic, ironic, sincere, elegiac, playful, grand. Not mutually exclusive — a wry song about unrequited love is comic *and* ironic and barely sincere |
| **advisories** | 27 | nine content dimensions (violence, sex, language, substance use, death, self-harm, religious content, positive messages, role models), each a 0–5 intensity plus two modifiers |
| **perspective** | 19 | how strongly the text fixes the gender of the singer and of the person the song is sung to — **and how hard that would be to change** |
| **sensitive** | 39 | thirteen subjects a particular student may need to avoid entirely, each with presence, centrality, and whether it is sung in first person |
| **age band** | 3 | `child` / `adolescent` / `adult`, worked out from the advisories by a published rule |
| **provenance** | 5 | which model answered, under which question set, and when |

### The two modifiers, which are the point

A flat violence score flags *Erlkönig*, *Butterfly*, *Carmen* and most of the Romantic lied —
which makes the column useless for its one job. So each advisory carries two more:

- `_first_person` — does the singer voice it **as themselves**?
- `_depicted` — does the text *show* it, or merely allude to it?

"I will die by my own hand" is a different thing to ask of a thirteen-year-old than "she died".
With these you can ask the question you actually have — *nothing my student has to sing as
themselves* — instead of *nothing violent*.

### Perspective: adaptability, not gender

The useful question is not *what gender is this song* but *how strongly is it cast, and can I
adapt it for this student*. So the columns report **mechanisms**, because mechanisms cost
different amounts to change:

| Mechanism | Example | Cost |
|---|---|---|
| none | much sacred and nature repertoire | 0 — nothing to change |
| pronouns | "I love **him**" | 1 — swap freely |
| gendered address | "sweet maid", "Mädchen" | 3 — needs a same-syllable substitute, often none exists |
| grammatical agreement | "sono stanc**a**", "je suis allé**e**" | 4 — every line ending may change; fine for a coach, conspicuous to an audience |
| named dramatic role | Cherubino, Don Giovanni | 5 — not adaptable without breaking the work |
| biology or life stage | pregnancy, "when I was a lad", widowhood | 5 — not adaptable |

`gender_adaptation_cost` is the worst of those that fire, and `gender_adaptation_blocker` names
which one it was. That pair is the answer to "can I give this to her?"

The love-interest columns are blank — not zero — when no specific other person is the song's
focus. A song can mention gendered people without any of them being the point, and there is
nothing to be undefined *about*. The gate is relational focus, not romance, so it also catches
the lullaby-to-my-son case.

### Sensitive subjects

Loss of a parent · loss of a child · loss of a sibling · loss of a partner · serious illness ·
suicide · self-harm · miscarriage or infant loss · family breakup · abandonment by a parent ·
war & displacement · abuse · addiction in the family.

Each gets three columns: is it there, how central is it (a passing line about a dead father is
not an elegy for one), and is it sung in first person.

**These never add up to a score, and that is deliberate.** Sensitivity is a relation between a
song and one particular student. Any number computed here would be pretending to know something
about your student, and `songfeat` stores nothing about any student — no column, no cache entry,
no log line. The songs carry flags; the knowledge of who has just lost their father stays with
you.

**The list will never be complete.** A student will arrive whose circumstance is not on it.

### Spend controls

| Flag | What it does |
|---|---|
| `--lyrics-estimate` | prints what a run *would* cost — calls, questions, tokens — and makes no network call |
| `--lyrics-questions core` | asks 13 questions instead of 153: one call per song, about 8% of the cost. Columns outside that set come back blank with a reason naming the set |
| `--lyrics-max-calls N` | stops making calls once the budget is hit, so a stray recursive glob cannot run up a bill |
| `--lyrics-cache PATH` | where to keep answers (default `.songfeat/jev-cache.sqlite`) |

**Answers are cached per question.** A second run over unchanged files makes **zero** calls and
produces a byte-identical file. Re-wording one question invalidates one column, not the whole
song. A lean `core` run's answers are reused by a later `full` run, which only asks the 140 it
has not asked yet.

The caching matters for a subtler reason too: the model's probabilities are not guaranteed to be
identical between calls, so **the cache, not the model, is what makes your library stable**. Two
databases built from the same scores at different times can differ slightly if either was built
from cold. The provenance columns are how that becomes visible rather than mysterious.

### The sidecar files

The full lyric text is written next to your output, in a `lyrics/` folder, one file per part —
not into a spreadsheet cell, where a 200-word text is miserable to work with. The
`lyrics_text_path` column names the file. This is how you check what was actually read before
you trust what it says.

---

## What these numbers do *not* mean

The most useful thing this document can do is tell you where the names mislead.

**`n_phrases` is not breaths.** It counts runs of notes between *notated rests*. Singers breathe
mid-line all the time where no rest is written, so on legato writing one "phrase" can run 30–80
seconds and span many real breaths. It does not measure breath demand. Treat it as "how the rests
are laid out".

**A probability is not a verdict.** `theme_love = 0.77` means the model leaned yes. It is not 77%
of the song, and it is not a 77% chance of being right.

**An advisory intensity is not a count.** The 0–5 scale is a probability-weighted average, so 2.4
is a real value meaning "between *present* and *central*", on this scale:

> 0 absent · 1 passing · 2 present · 3 central · 4 strong · 5 pervasive

**Blank means blank, never zero.** Every column that could not be determined is empty, and
`songfeat` goes to some trouble never to let an absence become a `0`. If a spreadsheet shows you
`0` for violence, the tool read the song and found none. If it shows you nothing, it did not
read it — and a reason column tells you why. This matters most for `age_band`, which is left
blank rather than ever guessing: a reassuring `child` about a song nobody read is the single most
harmful thing this tool could tell you.

**`age_band` is derived, not judged.** It comes from the advisory numbers by a published rule
(recorded in `age_band_rule` so a re-run is traceable), and `age_band_driver` names which
dimension decided it. It is not a recommendation. It is arithmetic on the advisories, and it is
blank whenever any advisory it reads is blank.

**Everything here is advisory.** Every column exists to inform your choice. None of them makes
it.

---

## Output formats

| Format | How | Notes |
|---|---|---|
| CSV | `-o library.csv` | one row per part; blank cells read as `NaN` in pandas |
| JSON / JSON Lines | `-o library.jsonl` | blanks are real `null`s |
| Google Sheets | `-f sheets -o "Sheet Name"` | **appends** — it does not deduplicate, so run twice and you get two copies of every row. Use a fresh worksheet per run |

Any sink can be told to leave columns out, which is how the provenance columns stay on the
record but off a teacher's spreadsheet — omitted deliberately, never lost by accident.

---

## Checking the tool against itself

```
songfeat scores/ --profile            # which columns are dead or redundant on your library
songfeat corpus/ --validate           # compare against the hand-checked ground-truth workbook
songfeat corpus/ --validate-lyrics dev  # per-column agreement for the lyric classifier
```

`--profile` tells you which columns are constant, empty, or duplicate each other *on your
particular library* — and distinguishes a column that is structurally dead (lyrics columns on a
MIDI folder) from one that merely happens to be flat on your files. It also now reports columns
it could not assess at all, instead of quietly dropping them.

`--validate-lyrics` reports agreement **per column, never as one headline number**, because the
axes are not equally learnable and an average would hide that. On the bundled 37-song corpus the
median per-column agreement is about 92%, with irony and the "positive messages" / "role models"
advisories much weaker than that.

**Those figures are an upper bound, not an accuracy estimate** — and the harness says so every
time it prints them. The songs, the labels and the question wording all come from the same
author, so a good result shows the plumbing works and obvious readings land. It cannot show the
hard cases are handled. Where the model and the label disagree, the song is logged for a human to
arbitrate rather than quietly scored away.

---

## Known limits

- **Lyric classification is validated in English only.** The teaching canon is substantially
  Italian, German and French. The questions are worded in English and the model's calibration in
  other languages is undocumented, so `lyrics_language` is reported from the start to make the gap
  visible in your data rather than assumed away. One Italian song is included in the test corpus
  to exercise grammatical agreement, which English cannot express; its figures carry their own
  caveat.
- **MIDI carries no words.** Every lyric column will be blank on a MIDI library.
- **Repeats and da capos are not expanded.** The text is taken as notated, once. A repeated verse
  adds no information and would distort word counts.
- **`narrator_gender` is what the *text* casts.** Trouser roles and performance tradition —
  Cherubino is a boy sung by a mezzo — are catalogue facts, not readable from the words, and are
  out of scope.
- **The thirteen sensitive subjects are not coverage.** The list grows by release.
- **Confidence is never exposed.** The model reports how concentrated its answer was, and that is
  deliberately not surfaced anywhere: it measures concentration, not correctness, and would be
  read as accuracy. The probabilities already carry the uncertainty that matters.

---

## For developers

Architecture, the `@feature` contract, the note-set rule, and the column budget are documented in
`songfeat/features/base.py` and in `docs/superpowers/specs/`. The decisions taken while building
the lyric group — including the ones that turned out wrong — are in
`docs/superpowers/decisions-2026-10-12-lyric-classification.md`.

Run the tests with `venv/bin/python -m pytest -q`. The two tests that call the real API are
marked `jev_live` and skipped without a key: `-m "not jev_live"` deselects them explicitly.

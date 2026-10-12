# Lyric classification: themes, tone, advisories and perspective

Design spec. Depends on `2026-10-10-songfeat-design.md` and the pipeline merged as PR #1.

## Intent

A voice teacher profiling their own song library wants to know what each song is *about*, not
only how hard it is to sing. The analytic features answer the second question. This group
answers the first, by reading the lyrics with a classifier model.

The use case that drove every decision here: a teacher choosing repertoire for a particular
student needs to find songs that fit, and — just as often — needs to rule songs *out*. Three
rule-out cases came from the teacher directly and shaped the design more than anything else:

- A student uncomfortable singing a love song to a specifically gendered love interest, or from
  a specifically gendered perspective. Sometimes a pronoun swap fixes it; sometimes it cannot be
  fixed at all. The teacher needs to know which, *before* assigning the song.
- A student for whom explicit content is inappropriate, where "explicit" has to mean something
  usable in a canon where half the repertoire ends in death.
- A student who has recently lost a parent, for whom songs about that loss must be avoided
  entirely, regardless of how good a fit they are otherwise.

This is one use of lyric classification among others, and it is advisory throughout. Every
column exists to inform a human's choice, never to make it.

## Scope

**In scope.** Extracting lyric text from a score; six axes of classification over that text;
caching, provenance and failure semantics; a purpose-built validation corpus.

**Out of scope.** Translation. Audio input. Any use of the classifier for the analytic features
(it is weak at counting and arithmetic — `songfeat` measures, the classifier judges). Storing
anything about a student. Automated repertoire *recommendation*: the output is a filterable
table, and the choosing stays with the teacher.

## Where this sits in the pipeline

A new feature group, `lyrics`, registered through the existing `@feature` contract. Three
properties distinguish it from every group already present:

1. **It is opt-in.** Everything in `songfeat` today is deterministic, offline and free. This
   group is none of those, so it runs only when named: `--groups lyrics` or an explicit
   include. A default run behaves exactly as it does now, and `schema(groups_filter)` already
   means the columns do not appear unless asked for. This matters because the group adds about
   177 columns to a 213-column schema.
2. **It requires lyric-bearing input.** `best_with = ("musicxml",)`. On MIDI — which is most of
   what exists, and all 150 files of the corpus that ships with Tessituragram — every column in
   the group is `None` with a reason. `--profile` already distinguishes a structurally dead
   column from one that is merely dead on this corpus.
3. **It calls a network service that costs money.** Hence the caching, provenance and secret
   handling below.

## Lyric extraction

Text assembly is deterministic and happens before any classification. MusicXML carries lyrics
as one `<lyric>` per note, which means the text has to be reassembled:

- **Syllables join into words** using the `syllabic` element (`begin`, `middle`, `end`,
  `single`). "Er-l-kö-nig" is four notes and one word.
- **Melisma extensions** (`<extend>`) carry no new text and must not produce empty tokens.
- **Elisions** (`<elision>`) join two syllables sung on one note.
- **Multiple verses** appear as `<lyric number="1">`, `number="2"` and so on. All verses are
  extracted and all are classified, in order. Strophic song is exactly where the later verses
  carry the turn — the gender reveal, the twist, the death — so first-verse-only would
  systematically misread the repertoire this serves.
- **Which part.** The part the existing vocal detector identifies. Where several parts carry
  lyrics, each produces its own row, as parts already do.

Repeats and da capo structures are *not* expanded: the text is taken as notated, once. A
repeated verse adds no information and would distort word counts.

### Columns

| Column | Type | Meaning |
|---|---|---|
| `lyrics_word_count` | int | words after reassembly |
| `lyrics_verse_count` | int | distinct `number` values found |
| `lyrics_language` | str | ISO 639-1, classified (see **Language** below) |
| `lyrics_sha256` | str | hash of the normalised text; the cache key and the audit anchor |
| `lyrics_text_path` | str | path to the sidecar text file |
| `lyrics_undefined_reason` | str | why the other columns are null, when they are |

The reassembled text is written to a **sidecar file**, not a table cell: a 200-word text in a
CSV cell is unpleasant to work with, and the Sheets path has a 50,000-character per-cell limit
that long texts would approach. The sidecar lets a teacher audit exactly what was classified.
Sidecar files are written next to the output file, in a `lyrics/` directory, named from the
source file's stem.

## The classifier

**Jev**, TypeSafe's classification model. Text plus a *typed question* in; a structured decision
with probabilities out. It never generates free-form text. Three question types are used:

| Type | Returns | Used for |
|---|---|---|
| `Noul` | a probability 0–1 that the answer is yes | every presence and mechanism flag |
| `Choice` | one of a fixed option set, plus a distribution over all options | gender, language |
| `Score` | 2–10 ordered levels, returning a probability-weighted mean that may fall between levels | advisory intensity |

Four properties of the model shape the integration:

**Questions batch against one shared state.** A single request carries many questions evaluated
in parallel against the same text. TypeSafe's own cookbook measures a batched call at 12.2×
cheaper and 10× faster than the same questions sent singly. The provider endpoint caps a call at
**20 questions**, so a song's 153 questions become 8 calls. (Verify this cap against the direct
API during implementation; if it is higher there, the batch size is a constant to change, not a
design to revisit.)

**Confidence is not accuracy.** TypeSafe's documentation is explicit: confidence "measures how
concentrated the probability distribution is, not the chance that the judgment is correct." Any
confidence column must say so in its description, or it will be read as accuracy. This is the
same class of error as a column named `n_phrases` that counts rest-delimited segments.

**It does not treat its input as hostile.** A lyric could contain text that reads like an
instruction. Mitigation: question text is a fixed constant in code, lyrics are passed only as
`state`, and nothing from the text is ever interpolated into a question. This does not make
influence impossible — it means the worst case is a wrong classification within a bounded,
typed output set, not an arbitrary action. Stated plainly rather than claimed as solved.

**Probabilities may not be bit-reproducible.** The cache, not the model, is what makes re-runs
stable. See Determinism below.

**Cost and latency.** 153 questions in 8 batched calls per song. The text is sent once per call
and each question's own text once, so roughly 6k input tokens per song. At $0.042 per million
input tokens with output unmetered, that is **under three cents per hundred songs**. Latency is
~300 ms per call, and the calls for one song may run concurrently.

## The six axes

Each axis is a registered feature whose `fields` are its columns, declared in one place
(`songfeat/features/lyrics/questions.py`) alongside the question text that produces it. The
vocabulary is fixed in code and versioned with releases, so every database built with a given
version is comparable.

### Axis 1 — Themes

Two tiers: 9 families, 56 children. Anchored on the Poetry Foundation's subject taxonomy, which
is already two-tier and was built for poems — art song texts *are* poems. Departures from it are
marked.

| Family | Children |
|---|---|
| Love | courtship & infatuation · desire & passion · devotion · unrequited · parting · complicated love · love lost |
| Relationships | friendship · family & ancestors · parent & child · siblings · home & belonging · betrayal & estrangement |
| Nature | seasons · weather · landscape & pastoral · sea & rivers · animals · night & stars · flowers & trees |
| Living | mortality · coming of age · aging · illness & healing · memory & nostalgia · solitude · dreams & sleep · time |
| Resilience & Self *(added)* | empowerment & agency · defiance · endurance · self-discovery & identity · grief turning to hope · courage |
| Religion & Transcendence | devotional & prayer · God & the divine · liturgical text · doubt & faith · the afterlife |
| Social Commentaries | war & conflict · exile & displacement · justice & protest · class & labour · race & ethnicity · gender & sexuality · city life |
| Activities & Craft | work · travel & journeys · music & singing · dancing · play & games · eating & drinking |
| Mythology & Folklore | myth & legend · fairy tale & enchantment · ghosts & the uncanny · folk & national tradition |

Three departures from the source taxonomy, each deliberate:

- **Friendship sits beside family, not inside it.** The Poetry Foundation lumps them as "Friends
  & Enemies". For repertoire they behave nothing alike, and `parent & child` in particular has
  to be findable on its own — it is what the bereavement case lands on hardest.
- **Resilience & Self is new.** "Empowerment" was on the teacher's list as a first-class term,
  and it is a stance the narrator takes rather than a subject the song is about.
- **Arts & Sciences is dropped**, its songs-about-music content folded into Activities & Craft.

**Empowerment means the narrator's stance within the text** — agency, defiance, self-assertion.
Not the song's message, and not the effect on the student. A lament of total helplessness can be
the most empowering thing a shy student sings all year, but that is a fact about the student;
the classifier reads only the text.

**Both tiers are asked independently**, and the family column reports what was asked, not the
maximum of its children. A third column per family, `theme_<family>_divergence`, is true when
the family fires but no child does, or vice versa. A divergence is not an error: it means either
the song's subject falls between the leaves, or a leaf fired spuriously. While the vocabulary is
young, those are the rows worth reading, so the column exists to surface them rather than to
reconcile them.

Columns: 9 family probabilities + 56 child probabilities + 9 divergence flags = **74**.

### Axis 2 — Tone

How a song treats its subject, as opposed to what it is about: `comic`, `ironic`, `sincere`,
`elegiac`, `playful`, `grand`. Six probabilities, not mutually exclusive — a wry song about
unrequited love is both comic and ironic and barely sincere.

This axis exists because "I need a comic song for a jury" is among the most common repertoire
requests, and humour is not a subject. Keeping it out of the theme hierarchy avoids one family
describing treatment while nine describe subject — the false symmetry that was rejected on the
perspective axis for the same reason.

Columns: **6**.

### Axis 3 — Content advisories

Nine dimensions, anchored on Common Sense Media's content grid, which teachers and parents
already read fluently. Consumerism is dropped (it barely occurs in this canon); death &
mortality, self-harm & suicide, and religious content are added. Religious content is a *filter*
need rather than a warning — it matters to teachers in secular schools and with students of
other faiths.

| Dimension | 0–5 intensity | why it is here |
|---|---|---|
| `positive_messages` | yes | useful *for* selection, not against it |
| `role_models` | yes | same |
| `violence` | yes | |
| `sex` | yes | |
| `language` | yes | profanity |
| `substance_use` | yes | |
| `death` | yes | added: art song is saturated with it, and it comes apart from violence constantly — a peaceful death-and-the-maiden text is not violent, and a comic duel is not about mortality |
| `self_harm` | yes | added: treated very differently from mortality in general by teachers and by school safeguarding guidance |
| `religious_content` | yes | added, as a filter |

Each dimension carries **three** columns:

- `advisory_<dim>` — intensity, 0–5, a `Score`.
- `advisory_<dim>_first_person` — probability that the singer voices it *as themselves*.
- `advisory_<dim>_depicted` — probability that the text depicts it rather than alluding to it.

The two modifiers are what make the axis usable on this repertoire. A flat violence score flags
*Erlkönig*, *Butterfly*, *Carmen* and most of the Romantic lied, which makes the column useless
for its one job. But the fix is not to discount period drama — a thirteen-year-old singing
Butterfly's suicide aria is a real pedagogical decision, not a false positive. What distinguishes
it from a contemporary explicit lyric is peculiar to *performed* repertoire: whether the student
has to inhabit it in first person. "I will die by my own hand" is a different thing to ask of a
student than "she died". With the modifiers, a teacher can ask the question they actually have —
*nothing my student has to sing as themselves* — rather than *nothing violent*.

Columns: 9 × 3 = **27**.

Note on deliberate overlap: `advisory_self_harm` and the sensitive subject `sensitive_suicide`
name related subject matter with **different semantics and different purposes**. The advisory is
a graded intensity that feeds the age band. The sensitive flag is presence and centrality, and
feeds nothing — it exists for per-student exclusion. This duplication is intentional and is
documented here because an undocumented term meaning two things in two modules is a defect this
project has already shipped once.

### Axis 4 — Perspective

The teacher's question is not *what gender is this song* but **how strongly is gender cast, and
can I adapt it for this student**. Adaptability is the deliverable; the gender itself is
secondary. So the axis reports mechanisms, because mechanisms have different adaptation costs:

| Mechanism | Example | Cost |
|---|---|---|
| none | much of the sacred and nature repertoire | nothing to change |
| pronouns | "I love **him**" | swap freely |
| gendered address | "sweet maid", "my lady", "Mädchen" | needs a same-syllable substitute, often none exists |
| grammatical agreement | "sono stanc**a**", "je suis allé**e**" | every line ending may change; feasible for a coach, conspicuous to an audience |
| named dramatic role | Cherubino, Don Giovanni | not adaptable without breaking the work |
| biological or life-stage specifics | pregnancy, "when I was a lad", widowhood | not adaptable |

Columns:

```
narrator_gender                       Choice: female | male | non-binary | collective | unspecified
narrator_gender_cast                  Score 0–5, derived from the mechanisms below
narrator_cast_by_pronouns             probability
narrator_cast_by_address              probability
narrator_cast_by_agreement            probability
narrator_cast_by_named_role           probability
narrator_cast_by_biology              probability

relational_focus_present              probability — is there a specific other the song centres on?
relationship_is_romantic              probability
addressee_present                     probability — is the song sung *to* someone?

love_interest_gender                  Choice, as above          } null unless
love_interest_gender_cast             Score 0–5                 } relational_focus_present
love_interest_cast_by_pronouns        probability               } is high
love_interest_cast_by_address         probability               }
love_interest_cast_by_agreement       probability               }
love_interest_cast_by_named_role      probability               }
love_interest_cast_by_biology         probability               }

gender_adaptation_cost                Score 0–5, max of the two cast scores
gender_adaptation_blocker             str — the mechanism that set the cost, or null
```

**The gate is relational focus, not romance.** The love-interest columns are `None` — not 0.0 —
when no specific other is the song's focus. This is what keeps a song like *Tom's Diner* quiet:
it contains gendered people, but none of them is a relational focus, so there is nothing to be
undefined *about*. Gating on relational focus rather than romance also catches the
lullaby-to-my-son case, which a teacher may want to filter for the same reason even though
nothing romantic is happening. `relationship_is_romantic` remains available as a sub-filter.

Narrator casting is **never** gated: a song written unmistakably from a man's perspective is
worth flagging whether or not anyone is being sung to.

`narrator_gender` reports the gender **the text casts**. Where performance tradition assigns a
role to a different voice — Cherubino is a boy sung by a mezzo, Handel's heroes are trouser
roles — that is catalogue metadata, not readable from the text, and is out of scope.

Columns: **19**.

### Axis 5 — Sensitive subjects

Thirteen flags, for finding the songs a particular student must not be given:

loss of a parent · loss of a child · loss of a sibling · loss of a partner · serious or terminal
illness · suicide · self-harm · miscarriage or infant loss · family breakup · abandonment by a
parent · war & displacement · abuse · addiction in the family

Each carries three columns: presence probability, `_centrality` (a passing reference to a dead
father differs from a song that is entirely an elegy for one), and `_first_person` ("my mother is
gone" is not "her mother was gone").

Three properties make this axis unlike the advisories:

1. **It never aggregates.** There is no composite sensitivity score, because sensitivity is a
   relation between a song and one student, and any number computed here would be pretending to
   know something about the student. Flags only.
2. **Centrality matters more than intensity.** Hence the second column rather than a 0–5 scale.
3. **The vocabulary will never be complete.** A student will arrive whose circumstance is not on
   the list. The list grows by release; the limitation is stated in the group's description so
   nobody mistakes thirteen flags for coverage.

**Privacy boundary, binding on this design: nothing about a student is stored, ever.** The songs
carry flags; the knowledge that a particular student has just lost their father stays with the
teacher, and the matching is ephemeral. This is the correct boundary on privacy grounds, and it
is also why no composite can exist.

Columns: 13 × 3 = **39**.

### Axis 6 — Age band

`child` / `adolescent` / `adult`, **derived** from the advisories by a documented rule, not asked
of the model. Three columns: `age_band`, `age_band_driver` (which dimension set it), and
`age_band_rule` (the rule version, so a re-derivation is traceable).

Bands rather than a numeric age because nothing in the validation data could justify the
difference between 13 and 14. Common Sense Media arrives at numeric floors through trained human
reviewers applying developmental guidelines we are not applying; borrowing the number would look
more precise than it is.

**Rule v1.** Evaluated in order; the first matching band wins:

```
adult       if  advisory_sex        >= 3
            or  advisory_violence   >= 4 and advisory_violence_depicted   > 0.5
            or  advisory_self_harm  >= 2 and advisory_self_harm_first_person > 0.5
            or  advisory_substance  >= 3
            or  advisory_language   >= 3

adolescent  if  advisory_sex        >= 1
            or  advisory_violence   >= 2
            or  advisory_death      >= 3 and advisory_death_first_person  > 0.5
            or  advisory_self_harm  >= 1
            or  advisory_language   >= 1

child       otherwise
```

`age_band_driver` names the triggering dimension with the highest intensity; ties break by the
declaration order in the table above, which is documented rather than incidental.

**`age_band` is `None` if any advisory it reads is `None`.** It may never default. A reassuring
`child` about a song nobody read is the one genuinely harmful output this design could produce.
Nor may it default the other way: a conservative fake `adult` is still a fake verdict, and it
would quietly hide most of the repertoire from the people this is for.

Columns: **3**.

### Language

`lyrics_language` is a `Choice` over ISO 639-1 codes. **The first version is validated in English
only.** Jev's cross-language calibration is undocumented, and a question worded for English may
quietly underperform in German; shipping a measured English-only claim is more honest than an
unmeasured multilingual one. The teaching canon is substantially Italian, German and French, so
this is a real limitation and the group's description says so. Question declarations are
structured to carry per-language variants later without reshaping anything, and the language
column exists from the start so the gap is visible in the data rather than assumed.

## Data contract

**Total: 177 new columns**, taking the schema from 213 to 390 when the group is requested — and
leaving it at 213 when it is not:

| Axis | Columns | Of which asked of the model |
|---|---|---|
| Lyric extraction | 6 | 1 (language) |
| Themes | 74 | 65 |
| Tone | 6 | 6 |
| Advisories | 27 | 27 |
| Perspective | 19 | 15 |
| Sensitive subjects | 39 | 39 |
| Age band | 3 | 0 — derived |
| Provenance | 3 | 0 |
| **Total** | **177** | **153** |

**Nulls are first class.** JSON has `null`; CSV writes an empty field, which pandas reads as
`NaN`; Sheets writes a blank cell, which charts and formulas distinguish from zero. The project
rule — *undefined means `None`, never 0.0* — applies unchanged.

**No booleans.** Every flag is a probability in 0–1, or `None`. A three-state boolean is the
0.0 hazard wearing a different hat: `if row["advisory_violence_first_person"]:` treats `None` as
`False`, so "we never read this song" silently becomes "no, the singer doesn't voice it". A
consumer comparing `> 0.5` against `None` gets a `TypeError` instead, which is the failure mode
we want. The `Choice` columns are strings with an explicit `unspecified` member, which is
distinct from `None`: `unspecified` means the text does not say, `None` means we did not ask.

**Provenance is mandatory on the record.** Three columns, always populated when the group ran:

| Column | Meaning |
|---|---|
| `clf_model` | the model id, e.g. `typesafe/jev-1.13` |
| `clf_question_set` | the version of the question declarations |
| `clf_classified_at` | ISO 8601 date of the classification (from the cache entry, not the run) |

Without these, a column means something different next year and nobody can tell. **A sink may
decline to write them**: the record defines the full schema and each sink carries its own
exclusion list, which is a small generalisation of the fact that `CsvSink` and `SheetsSink`
already disagree about which non-schema columns they emit. Provenance can therefore be omitted
from a teacher's spreadsheet deliberately, but never lost by accident.

## Failure semantics

| Condition | Result |
|---|---|
| No `JEV_KEY` | every column in the group `None`; reason: the key is absent |
| Input has no lyrics (all MIDI) | every column `None`; reason: no lyric events in the source |
| Lyrics present but empty after reassembly | every column `None`; reason names the count |
| API call fails or times out after retries | that batch's columns `None`; reason carries the status; other batches keep their values |
| A question returns an unparseable answer | that column `None`; reason names the question |
| `relational_focus_present` low | love-interest columns `None` by design, not by failure |

A partial result is a legitimate outcome: one failed batch nulls its own columns and no others.
The run exits non-zero only if every file failed, matching `pipeline.run`'s existing behaviour.

## Caching and determinism

Cache key: `sha256(normalised_text) + clf_model + clf_question_set`, where normalisation is
Unicode NFC, LF line endings, trailing whitespace stripped per line, and a single trailing
newline — defined explicitly because the cache key depends on it and a platform-dependent hash
would silently halve the hit rate. A hit returns the stored
answers and their original `clf_classified_at`; nothing is re-sent. Default location
`.songfeat/jev-cache.sqlite`, gitignored, path configurable.

This is what makes re-runs stable, since the model's probabilities are not guaranteed to be
bit-reproducible. Consequence worth stating: two databases built from the same scores at
different times may differ slightly if either was built cache-cold. The provenance columns are
how that becomes visible instead of mysterious.

Changing a question's wording bumps `clf_question_set` and invalidates exactly the columns that
question feeds — not the whole cache.

## Secrets and configuration

- **`.env.example`** committed, containing `JEV_KEY=` with a comment pointing at the README.
- **`.env`** stays gitignored. No key is ever read from a CLI argument, where it would land in
  shell history.
- **README section** stating what the key is for (classifying lyrics into themes, tone,
  advisories and perspective), what it costs (under three cents per hundred songs), and — the part
  people actually want to know — that everything else in the tool works without it. Adding the
  key enables one feature group; it is not a prerequisite for running anything.
- The key is read once at client construction. It never appears in a log line, an error message
  or a reason column. (`FileNotFoundError` leaking a credential path was a real finding in the
  previous plan's review; the same care applies.)

## Client

A `JevClient` protocol we define — `ask(state: str, questions: list[Question]) -> list[Answer]`
— with one concrete HTTP implementation over `httpx`. The protocol exists so that the official
SDK, or a different provider endpoint, is a swap behind a stable seam rather than a rewrite.
`httpx` and any SDK are **optional dependencies**, declared the way `gspread` already is: the
group reports `None` with a reason when the import fails, and the rest of the pipeline is
unaffected.

Batching, retry with backoff, and the 20-question cap live in the client, not in the features.
Retries are bounded and a budget is enforced per run, so a corpus run cannot silently spend more
than expected.

## Tests

**No test touches the network.** A `FakeJevClient` returns recorded fixtures, and the recorded
answers are committed. One integration test exercises the real API, is marked, and is skipped
unless `JEV_KEY` is present — so CI and a contributor without a key both see a green suite.

The existing project standard applies in full: assertions pin known values rather than asserting
thresholds, no test may pass unconditionally, and `tests/test_songfeat/test_assertions.py`
enforces what it can mechanically.

## Validation

### Corpus

About 36 purpose-built songs as MusicXML, with **original text** — no copyrighted lyrics enter
this repository. Synthetic rather than real repertoire because it is the only way to plant the
cases that matter:

- an obvious case per theme family, as a floor;
- metaphor, where the subject is never named;
- irony, where the literal reading is wrong;
- a gender reveal that arrives in verse three;
- a text that reads innocent line by line but not as a whole;
- a song with a gendered person who is *not* a relational focus (the *Tom's Diner* shape);
- each gender-casting mechanism in isolation, and two in combination;
- a bereavement text at low centrality (one passing line) and at high;
- a text with no gender markers at all;
- a comic text about a grave subject, and a grave text about a trivial one.

### Ground truth, and what it is worth

Labels are authored by hand and treated as truth. **The agreement figures this produces are an
upper bound, not an accuracy estimate** — the songs, the labels and the question wording all
come from the same author, so a green result demonstrates that the plumbing works and that
obvious readings land. It cannot demonstrate that the hard cases are handled. That is stated
here, in the group's description, and in whatever report quotes the numbers, for the same reason
the previous spec states where the reference data and the reference implementation disagree.

Four pieces of discipline preserve what validity is available:

1. **Songs and labels are frozen before any question wording is written**, and the freeze is a
   commit. This is the difference between a test and a mirror.
2. **A held-out slice of 12 songs is run once**, at the end. The real failure mode is tuning
   question wording until the test passes; a dev set and a held-out set make that measurable
   instead of invisible.
3. **Every disagreement is logged with its text and not adjudicated.** Where the model and the
   label differ, the song goes to a list for a human to arbitrate later.
4. **Agreement is reported per column**, never as one headline number, because the axes will not
   be equally learnable and an average would hide that.

If the teacher is ever willing to label two dozen songs independently, that upgrades to a real
inter-rater ceiling — model-vs-human agreement compared against human-vs-human agreement on the
same songs — for a couple of hours of their time. Worth asking; not a blocker.

### Harness

`--validate-lyrics <corpus>` prints per-column agreement against the committed labels, in the
shape `--validate` already uses. It reports the dev and held-out sets separately, and it never
reports a single composite.

## Changes to existing code

- **`profile.correlated_pairs` drops any column with a single null**, already a deferred minor.
  This group is null on every MIDI file, so the minor stops being cosmetic: the profiler would
  under-report redundancy exactly where it is likeliest. Fix it as part of this work.
- **Sinks gain an exclusion list**, for provenance and for anything a teacher does not want in
  their sheet.
- **`schema()` grows conditionally**, which it already supports through `groups_filter`.
- **`.gitignore`** gains the cache path and the lyric sidecar directory.

## Success criteria

1. A MusicXML file with lyrics produces populated columns on all six axes; the same file as MIDI
   produces `None` with a reason on every one of them, and never a zero.
2. No column in the group can report a value when the text was not read. Specifically: no
   advisory and no `age_band` has a default, in either direction.
3. A second run with a warm cache sends no requests and produces byte-identical output.
4. The suite passes with no `JEV_KEY` present, and no test reaches the network.
5. Per-column agreement is reported for the dev corpus and, once, for the held-out corpus, with
   the upper-bound caveat attached.
6. `--profile` reports the group's columns as structurally dead on a MIDI corpus, distinguishing
   that from a column that is dead merely on this corpus.
7. The 213-column schema is unchanged when the group is not requested.

## Deferred

- **Coupling gender-bearing syllables to note durations.** A pronoun held on a three-second note
  is not a free swap, and we already know every syllable's duration and phrase position. The
  schema leaves room; the first version does not attempt it.
- **Languages beyond English**, as above.
- **An inter-rater ceiling**, pending the teacher's time.
- **Mood as a distinct axis from tone.** Tone covers how a song treats its subject; a full
  valence/arousal or GEMS treatment of how it *feels* is a separate body of literature and a
  separate axis.
- **Verifying the 20-question cap against the direct API** rather than the provider endpoint.

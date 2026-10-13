# Decisions made while executing the lyric classification plan

Plan: `docs/superpowers/plans/2026-10-12-lyric-classification.md` (14 tasks).
Spec: `docs/superpowers/specs/2026-10-12-lyric-classification-design.md`.
Branch: `feat/lyric-classification`, 36 commits from `800ec71`.

Executed by subagents, one per task, each followed by a task review and, where needed, fix
rounds; then one whole-branch review, one fix wave and one scoped re-review. Where a review
finding conflicted with the plan's own text, or the plan was silent and the work could not
proceed without an answer, the decision was made rather than queued. Each is below with what
it costs if it turns out wrong, so any of them can be revisited cheaply.

Fifty-one decisions were recorded. Two findings were parked for a human rather than decided.
Nineteen smaller observations were deferred, triaged at the whole-branch review, and are listed
at the end.

**Three of these decisions were mine and wrong**, caught later by an implementer or a reviewer.
They are marked ✗ and kept in place rather than quietly corrected, because a plan's execution
record is worth less if it only shows the controller being right.

---

## The plan was wrong about the API, and that is the headline

The plan's prescribed wire format was wrong in **six** ways against the live service. This
surfaced only because Task 10's dispatch required its single live test to *pass*, not merely
to run.

- **A — the corrected wire format stands in full.** Wrong base path (404), wrong model string
  (400), `kind` instead of `type` as the question discriminator, `text` instead of
  `instructions` for the question text, `noul` rather than `probability` in Noul responses, and
  `criteria` omitted entirely though it is **mandatory** — without it the API returns "Noul
  question must have criteria or instructions". Corrected against live evidence, not guessed.
  *Cost if wrong:* nothing; it is verified against the service.
- **B — `Score` returns a probability-weighted mean that can land between levels**, confirmed
  in the docs and by a live call, so the client reads `score` directly and computes no mean.
  The advisory design's treatment of 2.4 as a real value is correct.
- **C — the 20-question batch cap is verified as a floor only.** The docs are silent; one live
  call carrying exactly 20 questions succeeded. The risk was one-directional: a cap *below* 20
  would fail every production run and no mocked test could catch it. Whether more than 20 is
  permitted remains unknown and stays in the spec's deferred list.
- **D — the generic `Score` criteria were a correctness problem, not cosmetics.** `_criteria()`
  sent `["level 0" … "level 5"]`. Harmless for `Noul` and `Choice`, but the age band tests
  *absolute* thresholds (`advisory_sex >= 3`, `advisory_violence >= 4`), which mean nothing
  unless 0–5 means the same thing on every song and every run. One shared, dimension-neutral
  rubric (`SCORE_LEVELS`) now ships with every Score question, plus an optional per-question
  override as the seam for the rubrics the spec defers. 153 authored rubrics were explicitly
  *not* attempted — that is design work for a human.
  *Cost if wrong:* the rubric is dimension-neutral where per-dimension would be sharper; the
  schema is unchanged, but re-wording it invalidates cached Score answers, since criteria are
  part of the cache key.
- **E — `clf_model` records the resolved model id, not the alias.** The alias `jev-latest`
  resolves server-side to a version; recording the alias defeated the provenance column's
  stated purpose. The **cache-keying half was deliberately deferred** and is documented in
  `client.py` and `cache.note_resolved_model`: rows stay keyed on the alias they were asked
  with, so one cache file cannot hold two model versions, and a roll-forward discards and
  re-asks the old version's rows rather than letting them coexist.

## Undefined must never become a number

The spec's central rule, and the source of the plan's one Critical defect.

- **F — a blank song must be refused, not classified.** `assemble_text` returned `None` only
  when a part had *no* lyric syllables; a part whose only syllable was whitespace returned
  `LyricText(text='', word_count=1, sha256=<hash of "">)`, so the classifier was called with an
  **empty state string** and reported real values — a measured `theme_love == 0.9` for a song
  with no words. Two further consequences: `word_count=1` asserted one word about no words, and
  every whitespace-only song collided on one cache key. `classify_part` now refuses with a
  reason naming the counts, and whitespace-only syllables are not counted as words.
  `assemble_text` deliberately still does **not** return `None` here, because the spec requires
  "no lyric events in the source" and "empty after reassembly" to stay distinguishable.
- **G — `age_band`'s null precondition is the nine columns rule v1 reads, not all 27.** The
  spec says `age_band` is `None` "if any advisory *it reads* is `None`", and it also commits
  that "one failed batch nulls its own columns and no others". Under the stricter reading, a
  failed batch carrying the `religious_content` questions would null `age_band` while all nine
  real inputs returned fine. Kept the simple all-nine precondition rather than short-circuiting
  per clause: an `adult` verdict from the first clause is safe without the later inputs, but a
  `child` verdict needs all nine, and a null-condition that varies by which clause fired is far
  harder to audit.
  *Cost if wrong:* `age_band` reports a band in a partial-result case a stricter reading would
  withhold; it can still never report one without having read every input.
- **H — `gender_adaptation_cost` gets the same all-or-nothing precondition.** `cast_score` took
  the max over whichever mechanisms happened to have answers, and because cost is a max, a
  missing mechanism could only **under**-report: cost 1 "swap freely" when the truth is 5 "not
  adaptable". Confirmed in real output — a live `core` run returned cost 0 with a null blocker
  on three songs, because `core` asks one of five mechanisms. That is the first driving use case
  inverted, so it now nulls unless all five of a subject's mechanisms answered.
- **I — `age_band_rule` populates when a derivation was *attempted*, and is `None` when the
  group never ran.** An earlier version of this decision had it always populated, on the
  grounds that the rule version is a fact about the derivation rather than a verdict about the
  song. That holds when inputs were missing; it does not hold on a MIDI file where nothing was
  derived, where it became the one column in the group reporting a value about text nobody read.
- **J — a `Choice` answer outside the declared option set becomes `None` with a reason, never
  `"unspecified"`.** `"unspecified"` means the text does not say; `None` means we did not ask or
  could not use the result. The plan's own sample code had no membership check, so this would
  have fallen through.
- **K — no composite sensitivity score anywhere**, enforced by a test banning
  `score|total|sum|index|overall|composite|max` in that axis's column names, and by there being
  no import path from `age.py` to `sensitive.py`.

## The error path

- **L — a classifier failure must cost one attempt, not seven.** The memo was written only on
  success, so each of the seven axis features independently re-entered `classify_part` —
  reproduced at **7 `ask()` invocations for one part**, up to 56 HTTP calls per song on a full
  run, with all 178 columns null and the reason column itself `None`. Reachable through the
  documented `--lyrics-max-calls` flag, not only exotic faults. Failures are now memoised with
  a readable reason, completed batches are banked before a budget stop propagates (those
  answers were paid for), `response.json()` is guarded, and an unexpected `question_id` becomes
  an `Answer(error=…)` rather than a `KeyError`.
- **M — `Answer.error` is surfaced.** Every axis discarded it, so the spec's failure rows
  requiring a reason that "carries the status" and one that "names the question" produced a bare
  `None`. Now summarised per axis into `record.errors`.
- **N — `client.MISSING_KEY` must be reachable.** With `--groups lyrics` and no key, the user
  was told "set JEV_KEY and request the 'lyrics' group" — advice to do what they had just done.
  `service.configure` now carries an unavailable reason; a default run with the group
  unrequested still reports `NOT_CONFIGURED`, which is the distinction worth keeping.
- **O — a failed sidecar write must not discard paid-for classifications.** The write preceded
  `yield record`, so an unwritable path took out that part and every later part of the same
  file. Paying an API bill and discarding the results because an audit file would not write is
  the wrong trade in every case.

## The cache

- **P — the cache key covers everything that determines an answer.** It was
  `sha256(question.text)`; the criteria — which for a Score question *are the scale the model
  answers on* — were outside it, so re-wording the shared rubric would have left stale answers
  matching their key while computed against a different scale, and one database would silently
  mix two scales. Now a canonical `fingerprint` over text, kind, options, levels and the
  **resolved** criteria, through one shared resolution helper the cache and client both call so
  they cannot disagree about what was asked. Neither task's review could have found this alone.
- **Q — `put_many` batches.** It looped over `put()`, which commits per call: ~140 transactions
  and fsyncs where one would do. The argument for per-call commits — a crash keeps answers
  already paid for — does not hold at these prices, where a whole song's 153 questions cost
  under three hundredths of a cent.
- **R — a hit returns the stored `classified_at`, never the run's clock**, because that
  timestamp is provenance in a column and a re-run must not rewrite when a song was classified.
- **S — a corrupt, locked or older-schema cache degrades to a miss and keeps the run alive**,
  with narrow handlers (`sqlite3.Error`, `OSError`) rather than a bare `except Exception` that
  would hide a real bug as a cache miss.

## The loader and music21

- **T — music21 was never verse-1-limited; the plan's premise was false.** Its getter is
  `'\n'.join(ly.text for ly in self.lyrics)` — every verse, newline-joined. What the old loader
  lost was verse *structure* (numbers, syllabic markers, elisions), not verse text; it stored
  all verses mashed into one string in a field documented as holding one.
- **U — `Note.lyric` means the lowest-numbered verse's text.** This is a real behaviour change,
  not the preservation the plan's constraint claimed. Every reader was checked: `vocal.py`,
  `basic.py` and `vocal_text.py` use it for truthiness only; `music21_adapter.py` relays the
  value to the jSymbolic `nat_language` extractor and now builds it from `note.lyrics` so it
  still relays every verse. No test moved, because the 150-file corpus is MIDI and carries no
  lyrics at all — which is how a change like this stays invisible.
- **V — composite (elided) lyrics flatten to one `Syllable` per component.** music21 *does*
  parse elisions fully (`Lyric.components`, `.elisionBefore`, `.isComposite`); the loader read
  only `.text`/`.syllabic`, so an elision arrived as one syllable marked `"composite"`, a value
  outside the begin/middle/end/single vocabulary. `"del l'al"` + `"ma"` assembled as three words
  instead of `"del l'alma"`. Italian and French are most of the teaching canon.
- **W — `Syllable.extend` stays declared but unsettable**, with a docstring saying so.
  music21 10.1.0 does not parse `<extend>` at all (`xmlToM21.py` carries a literal
  `# TODO: extend`), so an extend-only lyric arrives with no text and is dropped by the
  empty-text filter — which is the behaviour the spec wants anyway.
- **X — chord-borne syllables are deduplicated per onset.** The same `syllables` tuple was
  attached to every `Note` from a chord's pitches, so a two-note chord carrying one syllable
  produced `"ho ho ly"` / `word_count=3`. This corrupted the classified text, the cache key, the
  sidecar and `lyrics_word_count` on any divisi part.

## Opt-in

- **Y ✗ — my preflight decision that a bare `--schema` could keep 391 columns was wrong, and is
  reversed.** I accepted the plan's Done-when over the spec, which says plainly: "it runs only
  when named … **A default run behaves exactly as it does now**, and `schema(groups_filter)`
  already means the columns do not appear unless asked for." A default run emitted 391, of which
  178 were permanently empty. `schema(None)` is now 213; an explicit filter including `lyrics`
  is 391. One `_selected()` helper gates schema and extraction together so they cannot drift.
  Notably **no existing pinned count moved** — both pins pass an explicit filter, so the only
  numbers that changed were ones nothing asserted, which is how it survived fourteen reviews.
- **Z — the service configures only when the groups filter explicitly names `lyrics`**, not on
  a default run. The plan's form would have started spending the moment `JEV_KEY` existed in the
  environment, defeating the whole spend-control section.
- **AA — `--lyrics-cache PATH` was added**, closing a spec gap ("path configurable") and giving
  tests a way to stop writing a real 20 KB cache into the repository.

## The frozen corpus

- **AB — `cast-agreement` did not plant grammatical agreement, and English cannot plant it.**
  Its markers were "bride", "wife", "maid" — gendered *nouns* of marital life-stage. The spec's
  `agreement` mechanism means inflectional endings (`sono stanca`, `je suis allée`), so the song
  was relabelled `cast-life-stage` and a new short **Italian** song now plants real agreement.
  Its figure is uncalibrated — the spec validates English only — and that caveat is recorded in
  three places and printed by the harness.
  *Cost if wrong:* the corpus is 37 songs where the spec said "about 36", and one column's
  validation carries a caveat instead of a number.
- **AC — "when I was a lad" is `biology`, not `agreement`.** A review claimed otherwise; the
  spec lists that exact phrase under "biological or life-stage specifics". Rejected.
- **AD — `narrator_gender: "collective"` is a declared member of the spec's `Choice` set**, not
  an invention. Rejected.
- **AE — `love_interest_*` populated for non-romantic foci is exactly what the spec mandates**
  ("the gate is relational focus, not romance… catches the lullaby-to-my-son case"), and those
  are the spec's own column names. Rejected as out of scope, with a `_note` added to
  `labels.json` because the key name does mislead a reader of the raw labels.
- **AF — the two arguable labels must NOT be changed.** `cast-life-stage`'s
  `relational_focus_present: false` and `cast-agreement`'s thin theme labels were both flagged
  by their own author. The freeze-before-wording ordering is the only thing making this
  validation more than a mirror, and the harness already logs them as disagreements for a human
  to arbitrate. Changing a label now would spend the artifact's whole value to buy a nicer
  number.
- **AG — both the relabelled and the new Italian song sit in the held-out slice** (dev 24,
  held-out 13). Dev is where wording may legitimately be tuned, and agreement is the one column
  that must not be. The objection — that the single agreement case being held out hides a
  plumbing failure until the one-shot run — is answered by unit tests against a fake client,
  which is where "can this column ever fire" belongs.
- **AH — six frozen label keys needed aliases, not exclusion.** Four were already mapped; two
  more (`activities_eating`→`feasting`, `religion_devotional`→`prayer`) were not. All six are
  the corpus author and the vocabulary author picking different words out of one compound name
  in the spec. Excluding them would have left six of 56 theme children unvalidated, including
  the closest theme to the war-and-displacement concern the sensitive axis exists for.
- **AI — `UNMAPPABLE_LABEL_KEYS` fails loudly.** Its docstring previously said "nothing here
  treats an empty set as success or a nonempty one as failure", which is how a real gap read as
  a footnote. A test now pins it empty after scanning all 37 songs, and the harness reports any
  non-empty set prominently.

## The validation harness

- **AJ — Score columns are compared within ±0.5 of the labelled level**, stated in the output.
  22 columns (nine advisory intensities, thirteen centralities) were compared by exact equality
  against integer labels, which the model essentially never satisfies — a real run returned
  `advisory_violence = 0.64` and `centrality = 4.72`. The tolerance is declared, not derived.
- **AK — `lyrics_language` is reported as unlabelled rather than given an invented mapping.**
  The frozen corpus carries no language label; inventing one would be the harness labelling its
  own exam.
- **AL — the redundant `compare_corpus` call was removed.** That function issues the classifier
  calls, so calling it twice doubled the cost of every real validation run. Dev and held-out
  remain two independent calls, so the splits are still compared separately.

## Vocabulary and conventions

- **AM — `DIMENSIONS` is in rule-v1 trigger order** (`sex, violence, self_harm, substance_use,
  language, death, …`), not the Axis-3 presentation-table order. ✗ My dispatch stated the wrong
  one and the implementer overrode me, correctly: the plan, its pinned test and the spec's
  adult-clause order all agree, and it is the functionally meaningful order, since under the
  other reading the first two entries can never trigger any band.
- **AN — the derived cast scores are `int`, not `float`.** ✗ My global constraint was wrong. The
  float rule applies to values the *model* returns, where 2.4 is a genuine weighted mean; these
  are table lookups over five integer costs, so only 0, 1, 3, 4, 5 are reachable. The frozen
  labels are integers too, and `5.0` in a column meaning "not adaptable without breaking the
  work" is noise in a table a teacher reads. The fix pins the *type*, since `== 5` passes for a
  float.
- **AO — the modifier gates are strict `>`, not `>=`.** The spec's Rule v1 uses `> 0.5` in all
  three places; the plan's sample code used `>=`. Boundary tests pin 0.5 versus 0.51 on each.
- **AP — both theme tiers are asked independently and divergences are surfaced, never
  reconciled.** A divergence means the subject falls between the leaves or a leaf fired
  spuriously; while the vocabulary is young those are the rows worth reading. Every `core` run
  produces them on all nine families, since `CORE` asks `theme_love` plus one of love's seven
  children — a path that was initially untested.
- **AQ — `classify_part` always returns a `Classification`, never `None`.** One plan docstring
  and one interface line said otherwise; both contradicted the plan's own code and would have
  forced all eight axis modules to be rewritten.
- **AR — the group adds 178 columns, not the spec's 177.** The extra is
  `lyrics_classified_undefined_reason`: the five reasons a classification is missing belong to
  the classification rather than to any one axis. The spec's data-contract table was not updated
  and still says 177/390. **The spec should be corrected to 178/391.**
- **AS — `.gitignore` needed a negation.** The plan's bare `lyrics/` pattern has no leading
  slash, so it matched `songfeat/features/lyrics/` — the group's own source package. Had it
  shipped, `git add` would have silently skipped every new file in that package with no error.
  Caught only because an implementer ran `git check-ignore -v` instead of trusting the line.

## Process decisions

- **AT ✗ — running two implementers in parallel was wrong.** I checked their file sets were
  disjoint — they were — but the git *index* is itself shared state, so one agent's staged files
  were swept into the other's commit. The rule is about shared state, not overlapping paths. The
  outcome recovered without data loss because both agents independently refused to rewrite
  shared history mid-flight, which was the right instinct twice over. No further parallel
  implementers were dispatched.
- **AU — the real-API runs were deferred until after the whole-branch review.** The spec
  requires the held-out slice be run **once, at the end**; spending it against code about to
  change would waste the one measurement whose worth depends on being taken exactly once.
- **AV — tests that pass unconditionally were treated as a first-class defect, not a style
  note.** Eight of fourteen tasks needed an extra fix round on this. `test_assertions.py`
  catches the nested-`if`-in-loop shape but **not emptiness**: Task 4 shipped four tests that
  passed the checker while looping over an empty question set. Every loop now pins the count it
  checked. One instance was subtler — a CLI test never called `service.reset()` and leaked state
  into another module's test, which passed anyway because the leaked value coincidentally
  matched what it asserted.

---

## Parked: two questions left for a human

- **The `.songfeat` test-isolation guard has a latent hole.** A `conftest.py` fixture redirects
  `cache.DEFAULT_PATH` to a tmp path and asserts the repo file is untouched, which covers every
  code path that exists today. But a *future* `AnswerCache()` call with no argument would bind
  the default at import time and bypass the guard. The fix is two lines — make the parameter
  `path: str | None = None` and resolve in the body. Parked because the process allows one fix
  wave and it had closed; nothing downstream depends on it.
  *Cost if wrong:* a contributor adds a no-argument call and the suite writes into the working
  tree again — visible as a stray `.songfeat/`, which is how it was caught this time.
- **A green `age_band` row in the agreement table scores the model's advisories, not rule v1.**
  The printed table says nothing about that. This spec is unusually careful not to let a number
  claim more than it measures, so an uncaveated `age_band` row is the one place the harness
  overstates what it checked. One sentence in the output would close it.
  *Cost if wrong:* a reader treats a green `age_band` figure as validation of the age-band rule
  rather than of the advisories the rule reads.

## Deferred follow-ups

Triaged at the whole-branch review as **ship as is**, with reasons:

- `loaders.py` repeats an identical `Syllable(...)` construction in two branches — cosmetic.
- `meta.sidecar_name` returns `None` for a falsy `source_path`, so a one-field-null row is
  describable but not reachable: `FeatureRecord.source_path` is a required `str` and `load()`
  always sets it. Wants a docstring line, not a fix.
- `questions.register()` is import-order dependent with no reset hook — not reachable, since
  importing any submodule imports the package `__init__`; verified from five entry modules, all
  giving 153/13.
- `cache.py` uses `answer.__dict__` rather than `dataclasses.asdict` — correct while `Answer` is
  flat, and the round trip is pinned. `os.replace` clobbering an existing `.bak` discards a
  cache already treated as unreadable, and schema v2 does not exist.
- No test constructs `AnswerCache()` with the implicit `DEFAULT_PATH`; a direct test would have
  to write into the repo to be meaningful. Related to the first parked item.
- The sidecar collision registry keeps the plain name for whichever source claims it first, so
  ordering matters in principle; `cli.iter_score_files` returns `sorted(set(...))`, so it is
  stable in practice, and the column always records the name actually written.
- Two of three themes partial-coverage tests would pass under a coerce-to-`0.0` regression; the
  third catches it and uses the count-then-assert pattern.
- `test_lyrics_estimate_call_count_matches_a_real_run` parses a printed count by string
  splitting — brittle, though `predicted_calls > 0` guards vacuity and the comparison is real.
- `age` exposes `band_from(columns)` where the five classified axes expose
  `columns_from(answers)`; `meta` exposes neither. A naming convention worth stating once.
- `themes.columns_from` omits the `not answer.error` guard its five siblings carry — harmless
  only because every errored `Answer` is built with `probability=None`, so it is a latent
  coupling.
- The sink `exclude` list has no CLI surface; the spec requires the capability, not the flag.
- `--lyrics-estimate` ignores the text-hash memo, so it over-predicts for a multi-part score
  whose parts share text — the safe direction.
- `pytest.ini` declares the `jev_live` marker but does not default to deselecting it, so a bare
  `pytest` on a machine with `JEV_KEY` would spend money on two live calls. Both tests are
  marked *and* `skipif`'d, so the spec is satisfied.
- `criteria` for `Noul` and `Choice` remains generic placeholder text; the question's own
  `instructions` carries the judgment and the `Choice` option names are self-describing.
- The `base_url` is outside the cache key, which matters only for a provider swap.

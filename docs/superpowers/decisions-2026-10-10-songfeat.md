# Decisions made while executing the songfeat plan

Plan: `docs/superpowers/plans/2026-10-10-songfeat.md` (17 tasks).
Spec: `docs/superpowers/specs/2026-10-10-songfeat-design.md`.
Branch: `feat/feature-extraction`, 46 commits from `beaa4d4`.

The plan was executed by subagents, one per task, each followed by a review. Where a review
finding conflicted with the plan's own text, or the plan was silent and the work could not
proceed without an answer, the decision was made rather than queued for a human. Each one is
below with what it costs if it turns out wrong, so any of them can be revisited cheaply.

Forty-two were recorded under a label (A–AR, with AG and AH noted below). Four structural
findings were parked rather than decided, because they are spec-level questions about what a
measurement means. Forty-nine smaller observations were deferred to a triage list.

---

## Reversible conventions

- **A — CLI surface.** `--profile` and `--validate` are flags, not `songfeat profile` /
  `songfeat validate` subcommands as the spec's CLI block showed. The spec renders sibling
  do-one-thing-and-exit operations as flags already, so that block is illustrative.
  *Cost if wrong:* one argparse block plus the CLI test names.
- **B — `constants.py` belongs to Task 3**, despite being absent from its Files block.
  *Cost:* none; every consumer's import path fixes the location.
- **C — each extractor builds its own `PartContext`** rather than threading one shared context
  through the registry. The point of PartContext is definitional, not performance.
  *Cost:* ~7 context constructions per part instead of 1. No wrong numbers.
- **D — `Piece.notes_in_part` deleted**, made redundant by the part-centric model.
  *Cost:* trivially restorable.
- **E — Task 7 rewires the `extract` → `extract_part`/`extract_piece` imports**, so Task 2
  leaves the CLI briefly inconsistent. *Cost:* Task 7 discards interim code it rewrote anyway.
- **AF — the variance convention is documented.** `statistics.variance` (sample, ddof=1) is
  right — pandas' default — but a reader cross-checking against `np.var` (ddof=0) gets a
  different number with nothing on record. *Cost:* a word.

## Measurement definitions

These change numbers the pipeline reports. They are the decisions most worth re-reading.

- **H — the reference's ±0.1 Hz passaggio band tolerance is kept.** All nine bands' 18 edges
  are equal-tempered frequencies rounded to one decimal, so a strict comparison drops notes
  that are genuinely in the zone. Verified: with strict edges, medium/middle dwell reads 0.536 s
  against a ground truth of 21.321 s — a 40× error, because D4 (293.6648 Hz) sits just under
  the 293.7 edge. *Cost if wrong:* dwell seconds shift by one note's duration at zone edges.
- **I — `drop_trailing_marker` also shortens the piece's duration.** The reference's total time
  for aria I is the trailing marker's *onset*, not the file's end: 204.0 − 164.57 sounding
  = 39.43 rest, matching the sheet exactly. Dropping the marker's note while keeping its
  duration inflated piece extent by up to 1.4%. *Cost:* total time and every rate feature
  shift by under one marker duration.
- **W — a passaggio span breaks at a phrase boundary**, reusing `PHRASE_GAP_QUARTERS`, because
  sitting in the zone continuously is harder than two stints with a breath between.
  *Cost:* longest-span values shrink on pieces with mid-zone breaths, which is the correction.
- **Y — one shared definition of zone membership.** `n_leaps_crossing_passaggio` open-coded the
  test and so carried no edge tolerance while every `pass_*` feature did.
  *Cost:* that column counts more leaps, which is the correction.
- **AA — notes before the first lyric belong to no syllable.** The plan's grouping opened a
  group for a leading lyric-less note, so `len(groups)` exceeded `n_syllables`.
  *Cost:* leading unlyriced notes stop inflating melisma columns.
- **AO — `pass_*_pct` stays a dose ratio.** In the final fix wave I asked for the wall-clock
  union as the denominator; that is not implementable (a chord held in zone gives 400%). The
  bounded alternative, union over union, measured *worse* against the sheet (net −5 of 1350)
  and lets one voice's three registers sum past 100%. A dose over a dose is a proportion, and
  the over-count cancels. *Cost if wrong:* the nine percentage columns are a share of
  phonatory dose, not of elapsed time, so on an overlapping part they do not answer "what
  fraction of the time was she in this register". Add a new column; do not redefine `_pct`, or
  `_seconds` and `_pct` stop corresponding.

## Undefined must not be reported as a number

The spec forbids reporting an undefined quantity as `0.0` or any plausible value. It came up
five times.

- **V — two fabrications fixed.** `weighted_quantile` returned the middle pair when total
  weight was zero (reproduced: weights `[0,0,0]` returned 2.0 for q=0, q=0.5 *and* q=1), and a
  second site invented a value the same way. *Cost:* two fields return `None` in a degenerate
  case instead of a misleading number.
- **X — `leap_ascending_share` is `None` when there are no leaps.** Its denominator is the leap
  count, so a part with intervals but no leaps divided 0 by 0 and reported 0.0 — which reads as
  "all leaps descend". *Cost:* one column reads `None` on leap-free parts.
- **R — the 7 dynamics-dependent borrowed extractors are skipped.** Our `Note` carries no
  velocity, so they can never be recovered by enrichment, and they returned a confident 0.0.
  *Cost:* 7 fewer columns, all constant-zero padding.
- **T — multi-dimensional vectors are no longer summed.** jSymbolic's normalised histograms sum
  to exactly 1.0 for every file regardless of content, so `sum(result.vector)` manufactured a
  constant. Known ones are skipped by name; the rest return `None`.
  *Cost:* six fewer borrowed columns, all constant or lossy.
- **P — the borrowed count is 112, not 114.** Two instrument-fraction extractors leak through
  the plan's own skip list and fail the plan's own test.
  *Cost:* two columns omitted that were meaningless for one reconstructed part.
- **Q — `_as_score` relays tempo, key and meter.** `js_initial_tempo` read 120.0 — music21's
  default for a score with no MetronomeMark — while our model held the real 140.0.
  *Cost:* meter- and duration-derived borrowed features now derive from real marks.
- **U — and that fix needs a regression test**, since nothing asserted the tempo value.
  *Cost:* three tests tied to aria I's real tempo.

## The vocal detector

Four rounds on one signal. Recorded in full because the sequence contains two of my own errors.

- **J — fix the naming false positives.** Unanchored substring matching scored "Bass Clarinet"
  and "Alto Saxophone" as singers, above the 0.5 threshold — defeating the task's own
  acceptance criterion.
- **M — superseded by N.** I split the vocabulary into unambiguous and ambiguous words and put
  soprano, mezzo and baritone on the unambiguous side. Wrong: Soprano Saxophone, Baritone Horn.
  I had also first prescribed word-boundary matching, which does not help — "bass" is a whole
  word in "Bass Clarinet".
- **N — the principle is that instrument families are named by vocal register**, so every voice
  type is ambiguous and needs a companion word. *Cost:* an unusual vocal part name scores 0.0
  on a 0.10-weight signal.
- **O — tokenise on letter/digit boundaries, and validate against the real corpus.** This is
  the one that mattered: every corpus part is named `Voice1`, which tokenised to `["voice1"]`
  ≠ `"voice"`, so naming scored 0.0, every aria sat at 0.45, and the 0.5 threshold **rejected
  all 150 files**. After the fix, 149/150. *Cost:* "Soprano Line" and similar lose their match.
- **K — the empty-part branch still populates its evidence.** *Cost:* four dict keys.
- **L — the no-vocal case is tested against a real instrumental file** (music21's mozart/k155,
  whose parts are named Violin I/II and tagged "String Ensemble 1", exercising both halves of
  the naming rule) rather than a hand-built stub. *Cost:* a test that needs music21's corpus.

## Tests that could not fail

Seven of these. The pattern became a project standard in `CLAUDE.md` and a mechanical scanner
at `tests/test_songfeat/test_assertions.py`.

- **F — `assert not any(k.startswith("_error_") for k in out)`** passed unconditionally: the key
  is `_errors`, so the prefix never matched.
- **G — the zero-note test asserted only `pitch_range`'s fields**, leaving two feature groups
  unexercised on the input class the plan assigned to that task.
- **Z — `n_leaps_into_extremes` and `n_leaps_crossing_passaggio` had no assertion anywhere** —
  the only occurrences of either name in the diff were their own definitions. One of the two
  shipped ruling Y's defect.
- **AB — the no-gspread test proved nothing.** It blocked gspread via `sys.modules` and asserted
  `import songfeat` succeeded, but `songfeat/__init__.py` never imports the sinks.
- **AE — `weak_for_format`, `print_profile` and the `--profile` routing were untested**, so the
  one thing ruling AD added existed only as a manual run quoted in a report.
- **AK — the scanner was broadened, and my claim about it corrected.** It caught
  `if cond: assert` but not `if cond: continue` followed by a sibling assert — the more common
  Python idiom, and the one Task 17 used in all ten of its tests. `CLAUDE.md`'s
  "enforced by test_assertions.py" was an overclaim until this landed.
- **AL — three design-spec property invariants were restored**, having been implemented as
  weaker near-tautologies ("the longest phrase ≤ total time" is bounded by the timeline however
  phrases are cut).
- **AM — and one of those three, as I worded it, was unfalsifiable.** My own error, the
  sharpest of them: `_drop_trailing_marker` drops the marker only when no other note is at or
  below MIDI 24, so "a genuinely low aria keeps its lowest note" is true by identity. Verified
  on all three genuinely-low arias: byte-identical note lists either way. The test now asserts
  the refusal instead. *Cost:* a test name that describes what it checks.

## The validation harness

- **AI — the nine passaggio percentages are compared, not just the times.** The re-review
  thought them arithmetically redundant; they are not, and the counter-example is aria XCIX,
  where the time agrees and the percentage does not precisely because of the overlap finding
  below. Leaving them out would make the harness structurally unable to see the defect the
  harness itself surfaced. *Cost:* nine more rows in a report.
- **AJ — tolerances are justified per unit.** One `DEFAULT_TOLERANCE = 0.5`, justified in Hz,
  was being applied to seconds and about to be applied to percentages. Now `HZ_TOLERANCE = 0.5`,
  `SECONDS_TOLERANCE = 1.0`, `DOSE_TOLERANCE = 50.0`, `PASSAGGIO_SECONDS_TOLERANCE = 0.5`,
  `PASSAGGIO_PERCENT_TOLERANCE = 0.3`, each with its basis in a comment. The last was derived
  as roughly twice the corpus median residual and checked for tuning sensitivity across
  0.0–2.0 points, where it holds. *Cost:* the agreement percentages shift, which is the point.
- **AG — the passaggio figures must come from committed code, not a scratch script.** Recorded
  in the ledger's Task 16 narrative rather than under its own label. It paid for itself
  immediately: making the number reproducible is what revealed the scratch script had a bug —
  its 9-row block window ran into the next block's title row, because the LV and MV blocks sit
  exactly 8 rows apart, inflating two means to ~5.3 s and ~3.2 s. The committed harness's
  continuous scan does not have it.
- **AH — never substitute 0 for a `None` component** when combining quantities in `compare()`.
  Also recorded in-line rather than labelled. Still satisfied after AR: an unknown duration
  stays `None` and is reported as unmeasurable.
- **AR — `compare()` reads total time from the piece.** It had built `t` as
  `time_dose + rest`, which was right only by cancellation; once rest became wall-clock, `t`
  fell from 102/150 to 85/150. *Cost:* nothing measurable — `t` is back at 102/150.

## Scope decisions

- **S — the ~14-minute corpus runtime stands.** ~5.65 s per file, because `_as_score` is rebuilt
  once per extractor (112 reconstructions per part). *Cost:* a corpus run takes minutes, not
  seconds; the fix is a cache behind the same call site.
- **AD — `profile` surfaces `best_with`.** The spec says input-format availability is "recorded
  in feature metadata and surfaced by `profile`"; the plan never mentioned the field.
  *Cost:* one extra annotation in a report nobody must read.
- **AN — the Sheets key column is documented, not implemented.** The spec names it under
  practical constraints, so this is a requirement left unmet: re-running against the same
  worksheet appends duplicate rows. The docstring and `--help` say so.
  *Cost:* a user re-runs and must clear the sheet, having been warned.
- **AP — `rest_undefined_reason` is a free-text column.** A feature cannot write into
  `_errors` (the runner overwrites it), so a declared field is the only honest channel for
  "why is this `None`". *Cost:* one all-null string column in a numeric table.
- **AQ — two baseline figures that looked contradictory are the same measurement at different
  tolerances.** Before the fix I predicted rest agreement would go 31/150 → 49/150, measured at
  ±0.05 s. The shipped harness compares at ±1.0 s (ruling AJ) and measures 82/150 → 102/150.
  Both are right: at HEAD the union reads 49/150 at ±0.05, 86/150 at ±0.5 and 102/150 at ±1.0 —
  the prediction landed on 49 exactly. Recorded because I quoted the strict figure without its
  tolerance, which cost an implementer time chasing a phantom discrepancy.

---

## Parked: four questions that belong to a human

Each is a decision about what a measurement should mean, not a defect with a right answer.

1. **The vocal detector's calibration straddles its own threshold on lyric-less input.** Weights
   are lyrics 0.45, monophony 0.25, range 0.20, naming 0.10. With no lyrics the ceiling is 0.55
   and a monophonic in-range part already sits at 0.45 — so the 0.5 threshold falls *inside* the
   0.10 the name contributes, and every naming decision flips the verdict. That is why one
   signal produced three separate review findings. Our entire corpus is lyric-less. Retuning is
   a spec-level decision about what detection means.
2. **`PHRASE_GAP_QUARTERS` under-segments, and the cause is a units mismatch.** At 140 BPM,
   2.0 quarters is 0.857 s; aria I's gap distribution is bimodal with nothing between 0.5 and
   0.857 s, so the eighth-rests at 0.429 s are the real breath points and the threshold sits
   just above them. Result: 8 phrases across 204 s, one breath every 25 seconds, which no
   singer does. Breathing takes a fixed wall-clock time, but the threshold is in quarter notes,
   so the same constant means 2.0 s at 60 BPM and 0.857 s at 140. A seconds-based threshold
   was measured and segments *more coarsely* still (11-XI: 42.6 s → 117.8 s), so this needs
   calibration, not a sign flip. The affected columns were renamed in substance: their
   descriptions now say they count rest-delimited segments, explicitly not breath phrases.
3. **`js_quality` reads 0.0 across the corpus** while our own `analyzed_mode` varies major/minor
   on the same files. jSymbolic wants an explicit key mark carrying a *mode*; ruling Q inserts a
   KeySignature, which carries sharps and no mode (2 sharps is D major or B minor
   indifferently). Feeding it our *analysed* key would stack inference on inference. The spec's
   designed mitigation is what happened: `profile` reports the column as constant.
4. **`time_dose_seconds` sums note durations where notes overlap** — 74 of 150 arias. The
   arithmetic half of this is fixed: `rest_seconds` now subtracts a wall-clock union, the clamp
   that hid the overflow is gone, and agreement with the sheet rose 82/150 → 102/150 with zero
   regressions. What remains is definitional. Cumulative phonatory dose arguably *should* count
   a divisi stretch once per voice; wall-clock sounding time should not. If `time_dose_seconds`
   becomes a union, `rest_seconds` needs no change and `pass_*_pct`'s denominator moves with it.

## Residuals after the final review

The whole-branch review produced two Critical and eight Important findings; all ten were fixed
in one wave and verified. The scoped re-review of that wave returned eight further minors, none
blocking.

- **AS — three of them were fixed directly** rather than dispatched: a test guarding the
  ruling-AO partition claim used a pitch below every zone, so it passed with 33 points of
  headroom and never reached the case it existed to check (now midi 57, pinned at 99.99 — three
  33.33% shares, the 0.01 being the 2-decimal rounding); a docstring still named the old
  borrowed-feature count of 98; and `rest_undefined_reason` also fires on a zero-length piece,
  where rest is a real 0.0 and only its ratio is undefined, which the column name did not say.
  *Cost if wrong:* three edits in one fixture, one docstring and one description.
- **AT — five were parked.** Four are unreachable from any file on disk: a passaggio span that
  would publish an elapsed-time number on the same row where rest declares elapsed time
  unmeasurable; a null `onset_seconds` treated as time 0 in the union (reachable only from a
  hand-built `Piece`); and two Sheets header-check loosenings. The fifth has a real cost and is
  worth fixing before anyone uses the Sheets path in earnest: the refusal for a too-narrow sheet
  now fires at `close()`, after the whole corpus has been analysed and before anything is
  written, so the run's entire output is lost rather than just its error columns — and `run()`'s
  `finally: sink.close()` lets that error replace whatever exception was already in flight.
  A sixth was reported but is **not** introduced by this work: `dtype` is a per-feature string
  that no feature overrides and nothing reads, which has been true since Task 11.

---

## Deferred follow-ups

Forty-nine small observations were logged during the task reviews; the final whole-branch review
triaged them and named these twelve as worth keeping. None blocks a merge.

- `.mei` is advertised as an input format but never tested.
- `--list-features` omits `source`, `scope`, `dtype`, `citation` and `best_with`.
- `flat()` emits piece-level columns before part-level ones rather than in registry order
  (no sink is affected).
- `sustained_seconds` is an int where its siblings are floats.
- `pipeline.run` has duplicate `except` clauses, and `sink.open` sits outside the `try`.
- `_as_score` fabricates a 0.25 duration for a zero-duration grace note.
- `vocal._is_decoration`'s roman-numeral regex matches ordinary words ("Mill Soprano").
- There is no `tests/__init__.py`, though `test_properties` imports `tests.test_songfeat`.
- The ground-truth workbook path is relative, so `--validate` must run from the repo root.
- `Note.voice` and the `PartExtractor` alias are dead.
- Rounding drifts between 4 and 6 decimal places across the `*_share` columns.
- `profile.correlated_pairs` excludes any column with a single null, which under-reports
  redundancy exactly where it is likeliest.

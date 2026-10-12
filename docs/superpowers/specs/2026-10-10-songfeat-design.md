# songfeat: symbolic music feature extraction

**Date:** 2026-10-10
**Status:** approved design, not yet planned
**Scope of this spec:** library + CLI + output adapters, validated. Serving over
HTTP, caching, parallelism, composite scoring and any front-end are explicitly
out and get their own specs.

## Purpose

Turn a symbolic music file into a wide row of structured, documented features,
with emphasis on features that capture vocal skill and difficulty.

The intended consumer is a data scientist who will generate many features and
discover which matter empirically, using both analytical and qualitative
methods. That shapes two decisions that run through the whole design:

- **Breadth beats curation.** Where a feature set is well supported in the
  literature, use all of it rather than a hand-picked subset. Pruning before
  there is evidence discards signal that has not been measured.
- **No composite difficulty score.** A hand-weighted index would carry false
  authority. Emit components; let modelling decide the weights.

### Success criteria

1. Any supported file parses with no manual preprocessing. In particular, no
   file must be edited to add a reference pitch, which the existing CLI
   requires.
2. A multi-part score yields one row per part, and never pools a voice staff
   with a piano staff into a single pitch range.
3. Every emitted column carries metadata: source, group, scope, dtype,
   description, and a citation where one exists.
4. Adding a feature is a local change: one function, one registration, one test.
5. Nothing silently produces a wrong number. A failing feature nulls its own
   fields and records the reason against its name; a failing file is reported
   and skipped.

## Non-goals

- Instrument-specific models beyond voice (keyboard, guitar). The performer
  model is vocal-first.
- A single difficulty score.
- Serving uploads over HTTP.
- Any dependence on the upstream Django application.

## Architecture

Four stages, each independently testable:

```
load()          file ------> Piece   (parts, notes, tempo/key/meter maps)
prepare()       Piece -----> Piece   (marker stripping, part filtering)
detect_vocal()  Part ------> confidence 0..1 + the evidence behind it
extract()       Part ------> dict of features
```

### The part is the unit of analysis

`Piece` holds file-level metadata and a list of `Part`s; each `Part` owns its
notes. The currently committed model pools notes across parts, which is how a
voice-plus-piano file produces a meaningless range. Restructuring is cheap now
and expensive later.

### PartContext carries shared derivations

Expensive or definition-bearing derivations are computed once per part, lazily,
and cached on a `PartContext`:

- the interval sequence
- phrase segmentation by rest gaps
- sustained-note spans
- the prevailing key at each offset
- run detection

Features read from the context rather than recomputing. This is the main
defence against the failure mode where two features silently disagree about
what a "phrase" is.

### The registry gains a scope

Each extractor declares `scope="part"` or `scope="piece"`. Part-scoped features
run per part; piece-scoped features run once and are denormalised onto every
row. The music21 adapter marks extractors that are meaningless per-part rather
than emitting a plausible-looking wrong number.

### Output shape

One record per part. The record is a typed object, not a dict that happens to
become a CSV row --- see Output below.

## Vocal line detection

Returns a confidence in 0..1 with the evidence that produced it, so a wrong
guess is auditable rather than silent. Signals: presence of lyrics, degree of
monophony, plausible vocal range, instrument tag, part name. All parts are
analysed and emitted regardless; the score only flags the likely sung line.

## Feature groups

| Group | Source | Scope | Approx count |
|---|---|---|---|
| `basic` | ours (already built) | part + piece | ~30 |
| `jsymbolic` | music21 adapter | part | ~114 |
| `native` | music21 adapter | part | ~22 |
| `vocal` | ours (new) | part | ~45 |

`jsymbolic` and `native` wrap music21's existing extractors in full. They are
fast (measured: 6 extractors in 0.35s) and, in jSymbolic's case, a published and
citable set. The adapter owns namespacing (`js_` / `nat_` prefixes) and the
per-part score reconstruction that music21 requires.

### The vocal group

The part with no off-the-shelf equivalent.

**Tessitura and range**
- quartile boundaries Q0--Q4, emitted both duration-weighted and
  count-weighted as separate columns (see Validation --- the two definitions
  disagree in the reference data)
- tessitura width; compositional range; range relative to standard voice-type
  bounds

**Load**
- cycle dose (total vibrations), time dose, rest ratio
- sustained time above and below configurable thresholds

**Passaggi**

Passaggi are *zones*, not single break points. Upstream defines nine of them as
hardcoded frequency ranges at `src/tessitura.py:76-84` --- three voice types
(high / medium / low) by three registers (high / middle / low passaggio), for
example high voice middle passaggio = 311.1--392.0 Hz. We adopt these bands as
named, configurable constants rather than literals, and record their provenance.
Their pedagogical source is not cited in upstream code; the project's
bibliography page is the place to confirm it before publishing any result that
leans on them.

- dwell time and percentage per band, for each voice type
- *proximity*: time within +/-2 semitones of a zone edge, inside or outside
- number of zone crossings --- repeatedly crossing a passaggio is harder than
  sitting on one side of it
- longest continuous span inside a zone
- share of phrases beginning or ending inside or adjacent to a zone

**Breath and phrasing**
- phrase segmentation by rest gaps; longest phrase; mean phrase length
- count of phrases exceeding a breath-demand threshold

**Runs**
- count, maximum length, share of notes in runs, runs per minute
- mean run speed in notes per second
- melismatic runs tracked separately where lyrics exist: many notes on one
  syllable is a different demand from one note per syllable at speed

**Chromaticism**
- non-diatonic share against the prevailing key
- longest chromatic run; pitch-class entropy; accidental density

**Leaps**
- maximum leap; share of intervals above 2, 4 and 7 semitones
- leaps beyond an octave
- consecutive leaps without stepwise recovery
- unprepared leaps: not resolved by step in the opposite direction
- leaps landing in the extreme decile of the part's range
- ascending versus descending asymmetry --- not equally hard to sing
- *compound*: leaps that cross a passaggio zone

**Text**
- syllable count, melisma lengths, notes per syllable, melisma share

### Feature availability varies by format

MIDI carries no pitch spelling, so non-diatonic and accidental features must be
inferred against an analysed key and are weaker than the same features computed
from MusicXML, which carries real accidentals. Availability is therefore a
property of the input format, recorded in feature metadata and surfaced by
`profile`.

## Output

The pipeline produces typed records and hands them to a sink. Serialisation is
never done by the extraction code.

### The record

A Pydantic model, so the same object validates, serialises to JSON, and later
becomes an API response body without translation:

```python
class FeatureRecord(BaseModel):
    source_path: str
    source_format: str
    part_index: int
    part_name: str | None
    is_vocal_candidate: bool
    vocal_confidence: float
    features: dict[str, float | int | str | bool | None]
    errors: dict[str, str] = {}

    def flat(self) -> dict[str, Any]:
        """Identity fields merged with features, for tabular sinks."""
```

Identity fields are typed explicitly; the ~210 feature columns stay a mapping
rather than 210 model fields, because they are registry-driven and change as
features are added. `flat()` produces the wide row that tabular sinks want, in
stable registry order, so a schema change shows up in a diff.

Pydantic v2 becomes a dependency. It is not currently in `requirements.txt`.

### The sink protocol

```python
class Sink(Protocol):
    def open(self, schema: list[str]) -> None: ...
    def write(self, record: FeatureRecord) -> None: ...
    def close(self) -> None: ...
```

Streaming rather than collect-then-dump: a long batch can be consumed while it
runs, and the same shape serves a streaming API response later. The schema is
known from the registry before any file is parsed, so sinks that need a header
up front (CSV, Sheets) get one without a first pass.

Implementations in scope:

| Sink | Notes |
|---|---|
| `CsvSink` | wide rows via `flat()` |
| `JsonSink` | single array, convenient for small runs |
| `JsonlSink` | one record per line; the default for large batches |
| `SheetsSink` | appends rows to a Google Sheet |
| `MemorySink` | for tests |

### Google Sheets

The first non-file destination, and the reason the abstraction exists now
rather than later. Practical constraints to respect:

- Credentials come from a service account referenced by environment variable.
  Never committed, never logged.
- Rows are appended in batches, not one call per row --- the API quota is per
  minute and per user, and 150 files times several parts is enough to hit it.
- The header row is written on open only when the target sheet is empty.
- An optional key column (`source_path` plus `part_index`) supports re-running
  without duplicating rows.
- The Google client is an optional dependency. Importing `songfeat` must not
  require it; only constructing a `SheetsSink` does.

### Serving over an API

Out of scope here, and deliberately so. The design obligation this spec accepts
is narrower: `FeatureRecord` must serialise cleanly to JSON and expose a JSON
Schema, so that an API spec later adds a transport rather than reshaping the
core.

## Validation

Three layers, because the reference data and the reference implementation do
not agree with each other.

### 1. Ground truth harness

`tests/system_tests/Master Data Calculation.xlsx` holds one sheet per aria with
manually computed values: `t`, `tr`, `Q0p`--`Q4p`, `Fptp`, and passaggio times
and percentages. The harness parses all 150 sheets and reports per-aria deltas
against our values.

This is a **reporting** harness, not a pass/fail gate, because of the
discrepancy below.

**Observed on aria I:**

| Quantity | Spreadsheet | Upstream CLI |
|---|---|---|
| `t` (total time) | 204.0 s | 204.0 s |
| `tr` (rest time) | 39.43 s | 39.4 s |
| `Q0p` | 73.42 Hz | 73.4 Hz |
| `Q1p` | 130.81 Hz (C3) | 116.5 Hz (A#2) |
| `Q2p` (median) | 196.0 Hz (G3) | 185.0 Hz (F#3) |
| `Q3p` | 220.0 Hz | 220.0 Hz |
| `Q4p` | 329.63 Hz | 329.6 Hz |
| `Fptp` | 30738.44 | 30702.8 |

Extremes and durations agree exactly; two quartile boundaries differ by a
semitone or more. The likely cause is duration-weighted versus count-weighted
quantiles. **This has been checked on one aria only** and must be confirmed
across the corpus before any conclusion is drawn. Emitting both weightings lets
the harness determine which definition the manual data uses.

**Confirmed across all 150 arias** (Task 16, `songfeat/validation.py`):

| Quantity | Agrees w/ sheet | n | Mean delta |
|---|---|---|---|
| `Q0p` (min) | 140/150 | 150 | -0.06 |
| `Q4p` (max) | 145/150 | 150 | +1.20 |
| `Q1p` duration-weighted | 136/150 | 150 | -1.03 |
| `Q2p` duration-weighted | 129/150 | 150 | -2.04 |
| `Q3p` duration-weighted | 131/150 | 150 | -0.49 |
| `Q1p` count-weighted | 110/150 | 150 | -1.45 |
| `Q2p` count-weighted | 95/150 | 150 | -4.47 |
| `Q3p` count-weighted | 100/150 | 150 | -5.41 |

Duration weighting agrees with the spreadsheet substantially more often than
count weighting at every quartile (e.g. median 129/150 vs. 95/150), confirming
the aria I hypothesis as a corpus-wide pattern rather than a one-off. Neither
weighting reaches 150/150, so a residual, unrelated source of disagreement
remains for ~15-20% of arias even for the right weighting (see below).

`tr` (rest time) matched the sheet to float precision on aria I, but only
82/150 arias agree within 1 s corpus-wide (mean delta -1.54 s, stdev 4.3 s,
worst case -21.8 s). The failures are not randomly scattered: on the worst
arias, total time `t` still matches closely while `tr` is off by 10-20+
seconds, which only arithmetic allows if "sounding time" is overcounted by
the same amount. Checking one such aria (XCIX) directly: 64 of its 320 vocal
notes (20%) overlap the note before them in time -- `vocal_load` sums each
note's own duration without deduplicating overlaps, so overlapping notes
(ties, ornaments, or chord-like constructs in a nominally monophonic line)
inflate sounding time and deflate rest by the overlap amount. This also
explains most of the `Fptp`/cycle-dose divergence below. Flagged here as a
corpus-scale finding from Task 16's harness; fixing it is out of that task's
scope.

### 2. Cross-check against the reference implementation

Run upstream `main.py` across the corpus and diff its reported values against
ours. Any divergence is a defect in one implementation or the other, and the
comparison identifies which.

**Confirmed across all 150 arias:** `Q4p` (max) matches the CLI almost
exactly (150/150, mean delta 0.002 Hz) and `Q0p` (min) nearly so (147/150).
Cycle dose (`Fptp`/"Cycle Dose") is the surprise: it agrees with the CLI on
only 41/150 arias -- barely better than its 44/150 agreement with the
spreadsheet. On the 100 arias *without* the overlapping-note problem above,
our cycle dose matches the CLI to within 0.03 vibrations; on the ~50 that
have it, our value is inflated by hundreds to over ten thousand vibrations
relative to *both* references (which stay close to each other there). So the
aria I finding -- "cycle dose agrees with the CLI, not the sheet" -- does not
generalise as a reference-choice story; it generalises as "cycle dose agrees
with both references once the overlap bug is accounted for," which is a
different and more actionable conclusion.

**Passaggio offset (aria I: ~0.14 s in 5 of 6 non-high-register zones):**
confirmed as a small, non-proportional offset across the corpus. Restricting
to the middle/low-register zones with at least 1 s of dwell time (777 of
1350 zone/aria pairs), the median delta is 0.002 s and the median absolute
delta is 0.22 s -- consistent with aria I's ~0.14 s. The mean (0.37 s) and
stdev (2.1 s) are much larger because of a long right tail: correlation
between dwell time and delta is weak (Pearson r = 0.09), and the arias
contributing the largest passaggio deltas are the same ones with the
overlapping-note problem above, not long-dwell arias generally. So the
offset is neither cleanly constant (there is real spread) nor proportional
to dwell time (the correlation is too weak); it is a small, roughly flat
residual for most arias, polluted by the same overlap artifact that distorts
`tr` and `Fptp`.

### 3. Property tests

Invariants that hold regardless of definition:
- `Q0 <= Q1 <= Q2 <= Q3 <= Q4`
- dose and duration values are non-negative
- passaggio percentages sum within tolerance
- phrase durations sum to no more than total time
- dropping the reference marker never raises the minimum pitch of a part that
  genuinely sings that low

## The profile command

Runs a corpus and reports, per feature: null rate, variance, constant-ness, and
pairwise correlation above a threshold.

With ~210 columns against monophonic vocal input, a large fraction will be
degenerate --- jSymbolic includes features for instrumentation, chord types and
dynamics that are constant or null on a single-line MIDI. `profile` makes that
visible on the first run instead of after a modelling cycle.

## CLI surface

```
songfeat <paths...>                 files or folders
  -o, --out PATH                    path, or a Sheets URL/id
  -f, --format {json,jsonl,csv,sheets}
                                    inferred from --out when omitted
  -g, --groups basic,vocal          comma-separated groups
      --drop-trailing-marker        ignore the corpus reference pitch
      --no-recursive
      --list-features               describe features and exit
      --schema                      print column names and exit
  -q, --quiet

songfeat profile <paths...>         feature coverage report
songfeat validate <corpus>          ground-truth comparison report
```

## Error handling

A failing extractor nulls its own fields and records the reason in the record's
`errors` mapping, keyed by feature name. A failing file is reported to stderr
and skipped. A run producing at least one record exits 0.

Tabular sinks need errors as columns rather than a nested mapping, so `flat()`
emits one `_error_<name>` column per feature that actually failed in the run.
JSON and JSONL sinks keep the nested `errors` mapping. This replaces the
`_error_<name>` dict keys used by the currently committed implementation.

## Testing strategy

- **Unit**: per feature, against hand-built `Part` objects. Fast, no file I/O.
- **Integration**: real files in each supported format, including a multi-part
  score and a file with lyrics.
- **Property**: the invariants above.
- **Validation harness**: a reportable command, not part of the test suite,
  since it measures agreement with external data rather than correctness of
  code.

## Decisions recorded

- Vocal-first performer model, not instrument-aware or performer-agnostic.
- All parts analysed and emitted; vocal line flagged, never silently selected.
- music21 is a replaceable source of features, not the spine. Our model owns
  the public contract.
- Both quantile weightings emitted rather than choosing one before the evidence
  is in.
- No composite difficulty score in this scope.
- Output is a typed Pydantic record handed to a sink, not a dict serialised in
  place. Google Sheets is the first non-file sink; serving over an API is
  designed for but out of scope.

"""Invariants that hold whatever the feature definitions turn out to be.

Every test here loops over the corpus sample, so an empty or partially
loaded sample would make the whole file pass while asserting nothing.
`test_the_sample_loaded` exists to make that failure loud, and the
filtered tests count what they checked for the same reason. One
exception: the `marker_pairs` fixture below scans the full corpus, not
SAMPLE, because SAMPLE alone cannot exercise what its test checks -- see
that fixture's docstring.
"""

import os

import pytest

from songfeat.pipeline import analyze_file

CORPUS = os.path.join("data", "test_data_arias")
SAMPLE = [os.path.join(CORPUS, n) for n in sorted(os.listdir(CORPUS))[:12]]

#: Borrowed music21 extractors that fail on a reconstructed single part.
#: Imported from the adapter's own test module so the two cannot drift.
from tests.test_songfeat.test_pipeline import EXPECTED_BORROWED_FAILURES


@pytest.fixture(scope="module")
def records():
    out = []
    for path in SAMPLE:
        out.extend(analyze_file(path, drop_trailing_marker=True))
    return out


def test_the_sample_loaded(records):
    """Guards every other test in this file.

    All of them iterate `records`; an empty list would make each one pass
    vacuously. The corpus files are single-part, so one record per file.
    """
    assert len(SAMPLE) == 12, SAMPLE
    assert len(records) == len(SAMPLE), [r.source_path for r in records]


def _checked(values):
    """Assert a filtered test actually found something, then return it."""
    assert values, "filter matched no columns; the test would assert nothing"
    return values


def test_quartiles_are_ordered(records):
    seen = 0
    for record in records:
        f = record.features
        ordered = [f["q0_hz"], f["q1_hz_dur"], f["q2_hz_dur"], f["q3_hz_dur"], f["q4_hz"]]
        # Duration-weighted quartiles are None on a part with no sounding
        # time; the extremes stay real. Skip rather than crash on sorted().
        if any(v is None for v in ordered):
            continue
        seen += 1
        assert ordered == sorted(ordered), record.source_path
    assert seen, "no quartile sets were checked"


def test_count_weighted_quartiles_are_also_ordered(records):
    seen = 0
    for record in records:
        f = record.features
        trio = [f["q1_hz_cnt"], f["q2_hz_cnt"], f["q3_hz_cnt"]]
        if any(v is None for v in trio):
            continue
        seen += 1
        assert trio[0] <= trio[1] <= trio[2], record.source_path
    assert seen, "no count-weighted quartile trios were checked"


def test_durations_are_non_negative(records):
    seen = 0
    for record in records:
        for field in ("cycle_dose", "time_dose_seconds", "rest_seconds"):
            value = record.features[field]
            if value is None:        # rest_seconds is None when total time is unknown
                continue
            seen += 1
            assert value >= 0, (record.source_path, field)
    assert seen, "no duration values were checked"


def test_rest_ratio_is_a_proportion(records):
    seen = 0
    for record in records:
        value = record.features["rest_ratio"]
        if value is None:
            continue
        seen += 1
        assert 0.0 <= value <= 1.0, record.source_path
    assert seen, "no rest_ratio values were checked"


def test_passaggio_percentages_never_exceed_one_hundred(records):
    checked = _checked([
        (r.source_path, name, value)
        for r in records
        for name, value in r.features.items()
        if name.endswith("_pct") and value is not None
    ])
    for path, name, value in checked:
        assert 0.0 <= value <= 100.0, (path, name)


def test_phrase_time_does_not_exceed_total_time(records):
    """Bounded by the piece's own duration, not by sounding + rest.

    The old bound was `time_dose_seconds + rest_seconds`, which under the
    `max(total - sum, 0.0)` clamp equalled `max(sum, total)`: the bound
    inflated in lockstep with the duration sum's over-count, so no amount
    of over-counting could make it fail. The piece's total duration is an
    independent quantity, so this can now actually fail.
    """
    seen = 0
    for record in records:
        longest = record.features["phrase_longest_seconds"]
        total = record.features["duration_seconds"]
        if None in (longest, total):
            continue
        seen += 1
        assert longest <= total + 0.01, record.source_path
    assert seen, "no phrase durations were checked"


def test_shares_are_proportions(records):
    checked = _checked([
        (r.source_path, name, value)
        for r in records
        for name, value in r.features.items()
        if name.endswith("_share") and value is not None
    ])
    for path, name, value in checked:
        assert 0.0 <= value <= 1.0, (path, name)


def test_only_the_known_borrowed_features_error(records):
    """The error set is pinned, not asserted empty.

    Roughly a dozen jSymbolic and native extractors are unimplemented in
    music21 or meaningless on a reconstructed single part. Asserting zero
    errors would fail; asserting equality catches a NEW failure appearing
    or a known one silently disappearing.
    """
    failed = {name for r in records for name in r.errors}
    assert failed == EXPECTED_BORROWED_FAILURES, {
        "unexpected": sorted(failed - EXPECTED_BORROWED_FAILURES),
        "no longer failing": sorted(EXPECTED_BORROWED_FAILURES - failed),
    }


def test_every_record_has_the_full_schema(records):
    from songfeat.features import base
    expected = set(base.schema()) - set(type(records[0]).IDENTITY)
    assert expected, "schema minus identity columns was empty"
    for record in records:
        assert expected <= set(record.features), record.source_path


# --- three invariants from the design spec that the above narrowed away ---
#
# docs/superpowers/specs/2026-10-10-songfeat-design.md:357-365 lists five
# property-test invariants. Two are covered faithfully above (quartile
# ordering; non-negative dose/duration values). The other three were
# narrowed or dropped while this module was written and are restored here,
# each tested against the real thing the spec names rather than a proxy
# that happens to be easier to reach from a FeatureRecord.


@pytest.fixture(scope="module")
def pieces():
    """Parsed Pieces for SAMPLE, without running the feature battery.

    `phrase_longest_seconds` (checked against total time above) is bounded
    by the piece's own timeline almost by construction -- a single
    phrase's span can't exceed it barring a clock bug. The spec's actual
    claim is about the SUM of every phrase's span, which no feature
    exposes. Reusing `PartContext.phrases` and `_span_seconds` --
    `phrasing()`'s own building blocks, not a reimplementation of them --
    means this test checks the same thing the feature does, from the same
    input, instead of re-deriving it independently and risking a second,
    different bug.
    """
    from songfeat.loaders import load

    return [load(path, drop_trailing_marker=True) for path in SAMPLE]


def test_phrase_durations_sum_no_more_than_total_time(pieces):
    from songfeat.context import PartContext
    from songfeat.features.vocal_phrasing import _span_seconds

    seen = 0
    for piece in pieces:
        total = piece.duration_seconds
        if total is None:
            continue
        for part in piece.parts:
            if part.is_empty:
                continue
            spans = [_span_seconds(p) for p in PartContext(part, piece).phrases]
            seen += 1
            assert sum(spans) <= total + 0.01, (piece.source_path, part.index)
    assert seen, "no phrase-duration sums were checked"


def test_passaggio_percentages_sum_within_tolerance(records):
    """The three registers of one voice type are disjoint frequency zones.

    Checked against PASSAGGI's edges plus the shared 0.1 Hz edge
    tolerance (``vocal_passaggi._EDGE_TOLERANCE_HZ``): the narrowest gap
    between two adjacent zones for the same voice is the low voice's
    low/middle boundary, 246.9-261.6 Hz, which is 14.7 Hz -- far wider
    than the 0.2 Hz the tolerance could bridge. So a single note's
    sounding time lands in at most one of the three registers, and the
    three percentages should sum to **at most** 100 -- not necessarily to
    100, since a singer can spend time outside all three zones of a given
    voice type.

    Tolerance: each `_pct` is independently rounded to 2 decimal places
    from an unrounded fraction (``vocal_passaggi.passaggi``), so summing
    three of them can overstate the true sum by at most 3 * 0.005 = 0.015
    points. 0.1 leaves headroom over that bound while still catching a
    real defect: double-counted time would overshoot by whole points, not
    hundredths.
    """
    from songfeat.constants import PASSAGGI

    seen = 0
    for record in records:
        f = record.features
        for voice, registers in PASSAGGI.items():
            values = [f.get(f"pass_{voice}_{register}_pct") for register in registers]
            if any(v is None for v in values):
                continue
            seen += 1
            assert sum(values) <= 100.0 + 0.1, (record.source_path, voice, values)
    assert seen, "no passaggio percentage sums were checked"


@pytest.fixture(scope="module")
def marker_pairs():
    """(path, kept, dropped) for every corpus file, not just SAMPLE.

    This test needs a part that already has a second note at or below the
    marker pitch before dropping -- the exact condition
    ``loaders._drop_trailing_marker`` checks before refusing to drop
    anything. None of SAMPLE's 12 files has one: verified directly, every
    sampled file's only note at or below MIDI 24 (C1) is the trailing
    marker itself, so the guard's "leave it alone" branch is never
    exercised by SAMPLE. Three files in the full 150-file corpus do
    (18-XVIII.mid, 41-XLI.mid, 96-XCVI.mid -- each ends with the marker
    duplicated one note earlier). ``load()`` alone, with no feature
    extraction, costs about 3.6s for all 150 files (measured), so
    scanning the whole corpus here is cheap and does not touch or widen
    SAMPLE, which stays at 12 for every other test in this module.
    """
    from songfeat.loaders import load

    pairs = []
    # Deliberately the full corpus, not SAMPLE -- see the docstring above.
    # Every other fixture/test in this module reads SAMPLE; this is the
    # one exception, because SAMPLE alone cannot exercise what the test
    # checks.
    for name in sorted(os.listdir(CORPUS)):
        path = os.path.join(CORPUS, name)
        kept = load(path, drop_trailing_marker=False)
        dropped = load(path, drop_trailing_marker=True)
        pairs.append((path, kept, dropped))
    return pairs


def test_a_genuinely_low_part_keeps_its_trailing_marker(marker_pairs):
    """The falsifiable form of "dropping never raises the minimum pitch
    of a part that genuinely sings that low" -- which, as a pitch
    comparison between the kept and dropped loads, cannot actually fail.

    ``_drop_trailing_marker`` drops the trailing note *iff* it is the
    marker AND no other note sits at or below MIDI 24
    (``others = [...]; if others: return notes, None``). A part that
    "genuinely sings that low" is, by construction, exactly a part where
    `others` is non-empty -- so for every row this test can reach, the
    guard already refused to drop anything, and `kept` and `dropped`
    are the same note list. Comparing their minimum pitches is then true
    by identity, not by anything `_drop_trailing_marker` did: the
    spec's scenario ("a drop that would have raised the minimum of a
    genuinely low part") is structurally unreachable, because "drop
    happens" and "genuinely low" never co-occur in this implementation.
    That is the correct design -- it is *why* a genuine low C1 survives
    -- but it means the only thing left to test is the refusal itself:
    that nothing was dropped, and the marker is still there.
    """
    from songfeat.loaders import REFERENCE_MARKER_MIDI

    seen = 0
    for path, kept, dropped in marker_pairs:
        for kept_part, dropped_part in zip(kept.parts, dropped.parts):
            if kept_part.is_empty:
                continue
            # "Genuinely sings that low" is exactly what
            # _drop_trailing_marker itself checks: a note at or below the
            # marker pitch OTHER than the trailing one. Exactly one such
            # note (the marker alone) is the common case, excluded here;
            # two or more means the guard must refuse to drop anything.
            low_count = sum(
                1 for n in kept_part.notes if n.midi <= REFERENCE_MARKER_MIDI
            )
            if low_count < 2:
                continue
            seen += 1
            assert dropped_part.notes == kept_part.notes, (path, kept_part.index)
            assert dropped_part.notes[-1].midi == REFERENCE_MARKER_MIDI, (
                path, kept_part.index
            )
    assert seen, "no genuinely-low part was found anywhere in the corpus"


# --- Fix round 3: wall-clock sounding time ---------------------------------

@pytest.fixture(scope="module")
def sounding_cases():
    """(label, notes, piece_total) for every sample part, plus a chord.

    The corpus alone cannot falsify the invariant below. 74 of its 150
    arias do overlap, so a duration sum over-counts elapsed sounding time
    (worst: 96-XCVI.mid, by 29.3 s), but no corpus file overlaps enough
    for that sum to pass the piece's total — so substituting the sum for
    the union would leave a corpus-only test still passing, and the test
    would be asserting nothing about the distinction it exists to police.
    A chord-saturated part is appended for exactly that reason: it is the
    shape (any chordal or divisi part) where the sum provably exceeds the
    total, and it makes this property able to fail.
    """
    from songfeat.loaders import load
    from songfeat.model import Note, Part, Piece

    cases = []
    for path in SAMPLE:
        piece = load(path, drop_trailing_marker=True)
        for part in piece.parts:
            cases.append((path, part.notes, piece.duration_seconds))

    notes = [
        Note(midi=midi, onset=float(second) * 2, duration=2.0, part=0,
             onset_seconds=float(second), duration_seconds=1.0,
             is_chord_member=True)
        for second in range(10)
        for midi in (60, 64, 67, 72)
    ]
    synthetic = Part(index=0, notes=notes)
    cases.append((
        "<synthetic four-note chord repeated through a 10 s piece>",
        synthetic.notes,
        10.0,
    ))
    return cases


def test_wall_clock_sounding_time_never_exceeds_the_piece_total(sounding_cases):
    """The invariant that would have caught the rest-time error.

    A part cannot sound for longer than its piece lasts. Replace
    `union_seconds` with `sum(n.duration_seconds ...)` and the synthetic
    chordal case reports 40 s of sounding in a 10 s piece, failing here.
    """
    from songfeat.context import union_seconds

    assert len(sounding_cases) == len(SAMPLE) + 1, len(sounding_cases)
    for label, notes, total in sounding_cases:
        assert union_seconds(notes) <= total + 0.01, label


def test_the_duration_sum_really_does_over_count_on_this_corpus(sounding_cases):
    """Guards the test above from being a tautology.

    If union and sum agreed everywhere, the invariant would hold under
    either definition and prove nothing. They must measurably differ.
    """
    from songfeat.context import union_seconds

    differing = [
        label for label, notes, _ in sounding_cases
        if sum(n.duration_seconds or 0.0 for n in notes) - union_seconds(notes) > 0.01
    ]
    assert differing, "no sample part overlaps; the union/sum distinction is untested"


def test_rest_and_sounding_time_account_for_the_whole_piece(records):
    """rest_seconds is the piece's total minus wall-clock sounding time,
    with no clamp in between, so the two must close exactly."""
    from songfeat.context import union_seconds
    from songfeat.loaders import load

    seen = 0
    for path in SAMPLE:
        piece = load(path, drop_trailing_marker=True)
        for part in piece.parts:
            record = next(
                r for r in records
                if r.source_path == path and r.part_index == part.index
            )
            rest = record.features["rest_seconds"]
            if rest is None:
                continue
            seen += 1
            assert union_seconds(part.notes) + rest == pytest.approx(
                piece.duration_seconds, abs=0.02
            ), path
    assert seen, "no rest values were checked"


def test_passaggio_spans_never_exceed_the_piece_total(records):
    """A dwell span is elapsed time, so it is bounded by the piece.

    The old accumulator summed chord members' durations, which on a
    chordal part reports a span longer than the music.
    """
    checked = _checked([
        (r.source_path, name, value, r.features["duration_seconds"])
        for r in records
        for name, value in r.features.items()
        if name.endswith("_longest_span_seconds") and value is not None
        and r.features["duration_seconds"] is not None
    ])
    for path, name, value, total in checked:
        assert value <= total + 0.01, (path, name, value, total)

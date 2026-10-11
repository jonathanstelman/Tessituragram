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
    seen = 0
    for record in records:
        longest = record.features["phrase_longest_seconds"]
        sounding = record.features["time_dose_seconds"]
        rest = record.features["rest_seconds"]
        if None in (longest, sounding, rest):
            continue
        seen += 1
        assert longest <= sounding + rest + 0.01, record.source_path
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

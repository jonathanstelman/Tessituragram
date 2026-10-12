import os

import pytest

from songfeat.features import base
from songfeat.features.music21_adapter import (
    SKIPPED_EXTRACTORS, _as_score, register_music21_features, to_snake,
)
from songfeat.loaders import DEFAULT_BPM, load

ARIA = os.path.join("data", "test_data_arias", "1-I.mid")


def test_names_are_snake_cased():
    assert to_snake("AverageMelodicIntervalFeature") == "average_melodic_interval"
    assert to_snake("MostCommonPitchPrevalenceFeature") == "most_common_pitch_prevalence"


def test_adapter_registers_a_large_battery():
    """Pinned, not bounded.

    `> 90` could not fail while the real count was 98 and deliberate, so
    it asserted nothing about the number it exists to protect; a silent
    drop of seven extractors would have passed it. The count is the sum of
    deliberate, reviewed cuts: the brief's >100 less 7 dynamics extractors
    the model cannot supply (ruling R), 7 multi-dimensional vectors no
    honest scalar column could represent (ruling T), and 8 multi-voice
    extractors that returned a confident constant 0.0 against a single
    reconstructed line (fix round 3, finding 4). Changing this number is a
    decision, so it has to be made here rather than absorbed.
    """
    names = [n for n in base.registry() if n.startswith(("js_", "nat_"))]
    assert len(names) == 90, sorted(names)


def test_borrowed_features_are_namespaced_and_attributed():
    spec = base.registry()["js_average_melodic_interval"]
    assert spec.source == "jsymbolic"
    assert spec.scope == "part"
    # Name the source, so an empty or placeholder citation fails.
    assert "McKay" in spec.citation


def test_values_match_music21_run_directly():
    from music21 import converter
    from music21.features import jSymbolic

    piece = load(ARIA)
    out = base.extract_part(piece.parts[0], piece, groups_filter=["jsymbolic"])
    direct = jSymbolic.AverageMelodicIntervalFeature(
        converter.parse(ARIA)
    ).extract().vector[0]
    assert out["js_average_melodic_interval"] == pytest.approx(direct, rel=0.01)


def test_multipart_extractors_are_skipped():
    assert any("Instrument" in name for name in SKIPPED_EXTRACTORS)
    assert not any(
        n.startswith("js_") and "instrument" in n for n in base.registry()
    )


def test_empty_part_yields_none_rather_than_raising():
    from songfeat.model import Part, Piece
    piece = Piece(source_path="x.mid", source_format="midi", parts=[Part(index=0)])
    out = base.extract_part(piece.parts[0], piece, groups_filter=["jsymbolic"])
    assert out["js_average_melodic_interval"] is None


def test_multidimensional_vector_is_nulled_not_summed():
    """Ruling T (b): a vector with more than one element must raise --
    and so get nulled with the reason recorded -- rather than get summed
    into a fabricated scalar (jSymbolic's normalised histograms all summed
    to exactly 1.0 regardless of content). Exercised directly against a
    known 12-dimensional extractor, bypassing the by-name skip list
    entirely, so this proves the *general* defensive mechanism works --
    the backstop ruling T asked for against a future music21 extractor
    that is not yet in SKIPPED_EXTRACTORS by name.
    """
    from music21.features import jSymbolic
    from songfeat.features.music21_adapter import _make_extractor

    piece = load(ARIA, drop_trailing_marker=True)
    extractor = _make_extractor(jSymbolic.PitchClassDistributionFeature, "tmp")
    with pytest.raises(ValueError, match="12-element vector"):
        extractor(piece.parts[0], piece)


def test_no_currently_registered_feature_trips_the_vector_guard():
    """The by-name skip list (ruling T, part a) should already cover every
    vector-shaped extractor in this music21 version, so the defensive
    raise in ``_make_extractor`` (part b) is a backstop that should never
    actually fire for the 90 that remain registered.
    """
    piece = load(ARIA, drop_trailing_marker=True)
    out = base.extract_part(piece.parts[0], piece, groups_filter=["jsymbolic", "native"])
    errors = out.pop("_errors")
    assert not any("element vector" in message for message in errors.values())


def test_initial_tempo_reads_the_real_tempo_not_music21s_default():
    """Ruling Q: before enrichment this read 120.0 (music21's hardcoded
    default for a score with no MetronomeMark) on every file, looking like
    a measurement while being nothing but music21's fallback. Aria I's own
    notated tempo is 140.0 (also asserted independently on the ``basic``
    group's ``tempo_initial_bpm`` elsewhere) -- pinning this to a real file
    is the regression test ruling Q's fix was missing.
    """
    piece = load(ARIA, drop_trailing_marker=True)
    out = base.extract_part(piece.parts[0], piece, groups_filter=["jsymbolic"])
    assert out["js_initial_tempo"] == 140.0


def test_as_score_falls_back_to_default_bpm_with_no_tempo_mark():
    """The empty-marks path through ``_as_score``: a part with real notes
    but a piece that notates no tempo, meter or key at all. The existing
    empty-*part* test never reaches ``_as_score`` (it short-circuits on
    ``part.is_empty`` first), so this is the only test that actually
    exercises ``piece.tempos == []`` -- per the plan's Review Focus 3, that
    falls back to DEFAULT_BPM rather than raising or returning None.
    """
    from songfeat.model import Note, Part, Piece

    piece = Piece(
        source_path="x.mid", source_format="midi",
        parts=[Part(index=0, notes=[
            Note(midi=60, onset=0.0, duration=1.0, part=0),
            Note(midi=64, onset=1.0, duration=1.0, part=0),
        ])],
        tempos=[], meters=[], keys=[],
    )
    out = base.extract_part(piece.parts[0], piece, groups_filter=["jsymbolic"])
    # Some jSymbolic stubs raise regardless of input (unimplemented in this
    # music21 version -- see EXPECTED_BORROWED_FAILURES in test_pipeline.py);
    # that is unrelated to the no-tempo-mark path this test targets, so it
    # is enough that js_initial_tempo itself did not error.
    assert "js_initial_tempo" not in out["_errors"]
    assert out["js_initial_tempo"] == DEFAULT_BPM


def test_as_score_carries_a_mid_piece_tempo_change():
    """A tempo change is real information (the model's tempo-map machinery
    exists to carry it); ``_as_score`` must insert every mark at its own
    onset rather than only the first. Checked directly against the
    rebuilt score rather than through a single-valued feature, since no
    jSymbolic/native extractor reports "which tempos are present".
    """
    from music21 import tempo as m21_tempo
    from songfeat.model import Note, Part, Piece, TempoMark

    piece = Piece(
        source_path="x.mid", source_format="midi",
        parts=[Part(index=0, notes=[
            Note(midi=60, onset=0.0, duration=1.0, part=0),
            Note(midi=64, onset=10.0, duration=1.0, part=0),
        ])],
        tempos=[TempoMark(onset=0.0, bpm=80.0), TempoMark(onset=10.0, bpm=160.0)],
    )
    score = _as_score(piece.parts[0], piece)
    marks = list(score.parts[0].flatten().getElementsByClass(m21_tempo.MetronomeMark))
    found = {(m.offset, m.getQuarterBPM()) for m in marks}
    assert found == {(0.0, 80.0), (10.0, 160.0)}


# --- Fix round 3: the skip rule, applied to its own stated criterion -------

def test_multi_voice_extractors_are_skipped():
    """SKIPPED_EXTRACTORS' own rule: measured against one line these
    return a confident wrong number. Each of these compares voices with
    one another, or singles out the highest or lowest of several, and read
    a constant 0.0 across every aria in the corpus."""
    for name in (
        "VoiceEqualityNumberOfNotesFeature", "VoiceEqualityNoteDurationFeature",
        "VoiceEqualityMelodicLeapsFeature", "VoiceEqualityRangeFeature",
        "RangeOfHighestLineFeature", "RelativeNoteDensityOfHighestLineFeature",
        "MelodicIntervalsInLowestLineFeature", "VoiceSeparationFeature",
    ):
        assert name in SKIPPED_EXTRACTORS, name
    registered = set(base.registry())
    for column in (
        "js_voice_equality_number_of_notes", "js_voice_equality_note_duration",
        "js_voice_equality_melodic_leaps", "js_voice_equality_range",
        "js_range_of_highest_line", "js_relative_note_density_of_highest_line",
        "js_melodic_intervals_in_lowest_line", "js_voice_separation",
    ):
        assert column not in registered, column


def test_as_score_relays_lyrics():
    """`nat_language` read a constant 0.0 because `_as_score` relayed
    tempo, meter and key but not the lyrics `Note.lyric` carries -- the
    adapter's own argument against omitting information Piece already has.
    """
    from songfeat.model import Note, Part, Piece

    notes = [
        Note(midi=60, onset=0.0, duration=1.0, part=0, lyric="Lor"),
        Note(midi=62, onset=1.0, duration=1.0, part=0),
        Note(midi=64, onset=2.0, duration=1.0, part=0, lyric="em"),
    ]
    part = Part(index=0, notes=notes)
    piece = Piece(source_path="x.mid", source_format="midi", parts=[part])
    relayed = [n.lyric for n in _as_score(part, piece).flatten().notes]
    assert relayed == ["Lor", None, "em"]


def test_as_score_relays_all_verses():
    """The adapter must relay all verses, not just the convenience field.
    Multi-verse notes should have all verses joined by newlines in order."""
    from songfeat.model import Note, Part, Piece, Syllable

    notes = [
        Note(
            midi=60, onset=0.0, duration=1.0, part=0,
            lyric="Ky",
            lyrics=(
                Syllable(number=1, text="Ky", syllabic="single", extend=False),
                Syllable(number=2, text="Lord", syllabic="single", extend=False),
            ),
        ),
        Note(midi=62, onset=1.0, duration=1.0, part=0),
    ]
    part = Part(index=0, notes=notes)
    piece = Piece(source_path="x.mid", source_format="midi", parts=[part])
    relayed = [n.lyric for n in _as_score(part, piece).flatten().notes]
    # Both verses should be relayed, joined by newline in verse order (1, then 2)
    assert relayed == ["Ky\nLord", None]

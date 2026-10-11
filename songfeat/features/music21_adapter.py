"""Expose music21's jSymbolic and native extractors as songfeat features.

music21 remains a replaceable source of features: it supplies values, it
does not own the contract. Each part is rebuilt as a single-part score so
that extractors measure one line at a time.
"""

from __future__ import annotations

import re
from typing import Any

from music21 import note as m21_note
from music21 import features as m21_features
from music21 import key as m21_key
from music21 import meter as m21_meter
from music21 import stream
from music21 import tempo as m21_tempo
from music21.features import jSymbolic, native

from ..loaders import DEFAULT_BPM
from ..model import Part, Piece
from .base import feature

#: Skipped for two different reasons -- worth keeping apart, because they
#: carry different implications for whether a future music21 version or a
#: richer model could un-skip them.
SKIPPED_EXTRACTORS = {
    # Instrumentation / multi-part texture: meaningless for a single
    # reconstructed part regardless of what the model carries. Measured
    # against one line they would return a confident wrong number.
    "AcousticGuitarFractionFeature", "BrassFractionFeature",
    "ElectricGuitarFractionFeature", "ElectricInstrumentFractionFeature",
    "InstrumentFractionFeature", "InstrumentsPresentFeature",
    "PitchedInstrumentsPresentFeature", "NumberOfPitchedInstrumentsFeature",
    "NumberOfUnpitchedInstrumentsFeature", "OrchestralStringsFractionFeature",
    "PercussionPrevalenceFeature", "SaxophoneFractionFeature",
    "StringEnsembleFractionFeature", "StringKeyboardFractionFeature",
    "ViolinFractionFeature", "WoodwindsFractionFeature",
    "UnpitchedInstrumentsPresentFeature", "NotePrevalenceOfPitchedInstrumentsFeature",
    "NotePrevalenceOfUnpitchedInstrumentsFeature",
    "TimePrevalenceOfPitchedInstrumentsFeature",
    "VariabilityOfNotePrevalenceOfPitchedInstrumentsFeature",
    "VariabilityOfNotePrevalenceOfUnpitchedInstrumentsFeature",
    "MaximumNumberOfIndependentVoicesFeature",
    "AverageNumberOfIndependentVoicesFeature",
    "VariabilityOfNumberOfIndependentVoicesFeature",

    # Dynamics: ``Note`` carries no velocity/dynamic at all, so unlike
    # tempo/meter/key this is not something a richer ``_as_score`` could
    # recover -- the model simply does not have the data. Left registered,
    # these would read 0.0 for every part, indistinguishable from a real,
    # measured absence of dynamic variation.
    "AverageNoteToNoteDynamicsChangeFeature", "ImportanceOfLoudestVoiceFeature",
    "OverallDynamicRangeFeature", "RelativeRangeOfLoudestVoiceFeature",
    "VariationOfDynamicsFeature", "VariationOfDynamicsInEachVoiceFeature",
    "VoiceEqualityDynamicsFeature",
}

CITATIONS = {
    "jsymbolic": (
        "McKay, C. and Fujinaga, I. (2006). jSymbolic: A feature extractor "
        "for MIDI files. ICMC."
    ),
    "music21-native": (
        "Cuthbert, M. S. and Ariza, C. (2010). music21: A toolkit for "
        "computer-aided musicology. ISMIR."
    ),
}


def to_snake(class_name: str) -> str:
    """AverageMelodicIntervalFeature -> average_melodic_interval"""
    stem = class_name[: -len("Feature")] if class_name.endswith("Feature") else class_name
    return re.sub(r"(?<!^)(?=[A-Z])", "_", stem).lower()


def _as_score(part: Part, piece: Piece) -> stream.Score:
    """Rebuild one normalised part as a music21 score.

    Tempo, meter and key are real information ``Piece`` already carries
    (not reconstructed, just relayed), and several extractors key off them
    directly -- e.g. initial tempo, rhythmic pulse strength. Leaving them
    out does not make those extractors return null; it makes them return
    music21's hardcoded default (120 BPM, no signature), which looks like
    a measurement and is not one. A piece with no tempo mark falls back to
    the same DEFAULT_BPM the rest of songfeat uses for an unmarked piece,
    so duration-weighted extractors still compute. No meter or key mark
    means none is inserted -- there is no equivalent "default signature"
    to fall back to without inventing one.

    Every mark is inserted at its own onset, including mid-piece changes:
    a tempo or meter change is real information the model's tempo-map
    machinery exists to carry, not a detail to flatten away.
    """
    line = stream.Part()
    for mark in (piece.tempos or [None]):
        bpm = mark.bpm if mark is not None else DEFAULT_BPM
        onset = mark.onset if mark is not None else 0.0
        line.insert(onset, m21_tempo.MetronomeMark(number=bpm))
    for mark in piece.meters:
        line.insert(mark.onset, m21_meter.TimeSignature(mark.symbol))
    for mark in piece.keys:
        line.insert(mark.onset, m21_key.KeySignature(mark.sharps))
    for note in sorted(part.notes, key=lambda n: n.onset):
        element = m21_note.Note(note.midi)
        element.quarterLength = note.duration or 0.25
        line.insert(note.onset, element)
    return stream.Score([line])


def _make_extractor(cls, column: str):
    def extract(part: Part, piece: Piece) -> dict[str, Any]:
        if part.is_empty:
            return {column: None}
        result = cls(_as_score(part, piece)).extract()
        value = result.vector[0] if len(result.vector) == 1 else sum(result.vector)
        return {column: round(float(value), 6)}

    return extract


def register_music21_features() -> int:
    registered = 0
    for module, group, source in (
        (jSymbolic, "jsymbolic", "jsymbolic"),
        (native, "native", "music21-native"),
    ):
        for attribute in vars(module).values():
            if not isinstance(attribute, type):
                continue
            if not issubclass(attribute, m21_features.FeatureExtractor):
                continue
            if attribute is m21_features.FeatureExtractor:
                continue
            if attribute.__name__ in SKIPPED_EXTRACTORS:
                continue
            prefix = "js_" if group == "jsymbolic" else "nat_"
            column = prefix + to_snake(attribute.__name__)
            feature(
                name=column, group=group, scope="part", source=source,
                description=(getattr(attribute, "description", None)
                             or attribute.__name__),
                fields=(column,), citation=CITATIONS[source],
            )(_make_extractor(attribute, column))
            registered += 1
    return registered

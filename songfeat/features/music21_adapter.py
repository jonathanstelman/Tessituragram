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
from music21 import stream
from music21.features import jSymbolic, native

from ..model import Part, Piece
from .base import feature

#: Extractors that describe instrumentation or multi-part texture. Measured
#: against a single reconstructed part they would return a confident wrong
#: number, so they are not registered at all.
SKIPPED_EXTRACTORS = {
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


def _as_score(part: Part) -> stream.Score:
    """Rebuild one normalised part as a music21 score."""
    line = stream.Part()
    for note in sorted(part.notes, key=lambda n: n.onset):
        element = m21_note.Note(note.midi)
        element.quarterLength = note.duration or 0.25
        line.insert(note.onset, element)
    return stream.Score([line])


def _make_extractor(cls, column: str):
    def extract(part: Part, piece: Piece) -> dict[str, Any]:
        if part.is_empty:
            return {column: None}
        result = cls(_as_score(part)).extract()
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

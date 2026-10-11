import os

import pytest

from songfeat.features import base
from songfeat.features.music21_adapter import (
    SKIPPED_EXTRACTORS, register_music21_features, to_snake,
)
from songfeat.loaders import load

ARIA = os.path.join("data", "test_data_arias", "1-I.mid")


def test_names_are_snake_cased():
    assert to_snake("AverageMelodicIntervalFeature") == "average_melodic_interval"
    assert to_snake("MostCommonPitchPrevalenceFeature") == "most_common_pitch_prevalence"


def test_adapter_registers_a_large_battery():
    names = [n for n in base.registry() if n.startswith(("js_", "nat_"))]
    assert len(names) > 100


def test_borrowed_features_are_namespaced_and_attributed():
    spec = base.registry()["js_average_melodic_interval"]
    assert spec.source == "jsymbolic"
    assert spec.scope == "part"
    assert spec.citation is not None


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

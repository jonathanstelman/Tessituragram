import json

import pytest

from songfeat.record import FeatureRecord


def make_record(**overrides) -> FeatureRecord:
    base = dict(
        source_path="song.mid",
        source_format="midi",
        part_index=0,
        part_name="Voice",
        is_vocal_candidate=True,
        vocal_confidence=0.97,
        features={"min_midi": 60, "max_note": "A4"},
    )
    base.update(overrides)
    return FeatureRecord(**base)


def test_flat_merges_identity_and_features():
    flat = make_record().flat()
    assert flat["source_path"] == "song.mid"
    assert flat["min_midi"] == 60
    assert "features" not in flat


def test_flat_projects_errors_to_columns():
    flat = make_record(errors={"tessitura": "ValueError: bad"}).flat()
    assert flat["_error_tessitura"] == "ValueError: bad"


def test_flat_omits_error_columns_when_there_are_none():
    assert not any(k.startswith("_error_") for k in make_record().flat())


def test_round_trips_through_json():
    record = make_record()
    restored = FeatureRecord.model_validate_json(record.model_dump_json())
    assert restored == record


def test_confidence_is_bounded():
    with pytest.raises(ValueError):
        make_record(vocal_confidence=1.5)


def test_exposes_a_json_schema():
    """The spec's obligation to a future API."""
    schema = FeatureRecord.model_json_schema()
    assert "vocal_confidence" in schema["properties"]

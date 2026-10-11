import pytest

from songfeat.features import base
from songfeat.model import Note, Part, Piece


def test_spec_carries_metadata():
    spec = base.registry()["pitch_range"]
    assert spec.scope == "part"
    assert spec.source == "songfeat"
    assert spec.citation is None or isinstance(spec.citation, str)
    # None means equally valid for every format.
    assert spec.best_with is None


def test_scope_must_be_part_or_piece():
    with pytest.raises(ValueError):
        base.feature(
            name="bad", group="basic", scope="movement", source="songfeat",
            description="", fields=("x",),
        )(lambda part, piece: {"x": 1})


def test_part_scoped_feature_sees_only_its_part():
    piece = Piece(
        source_path="x.mid",
        source_format="midi",
        parts=[
            Part(index=0, notes=[Note(midi=60, onset=0.0, duration=1.0, part=0)]),
            Part(index=1, notes=[Note(midi=36, onset=0.0, duration=1.0, part=1)]),
        ],
    )
    out = base.extract_part(piece.parts[0], piece)
    assert out["min_midi"] == 60


def test_empty_part_yields_none_not_an_exception():
    """Review Focus 1: a rest-only or empty staff."""
    piece = Piece(source_path="x.mid", source_format="midi", parts=[Part(index=0)])
    out = base.extract_part(piece.parts[0], piece)
    assert out["min_midi"] is None
    assert out["range_semitones"] is None
    assert out["n_notes"] == 0
    assert not any(k.startswith("_error_") for k in out)


def test_failing_extractor_is_isolated():
    @base.feature(
        name="boom", group="basic", scope="part", source="songfeat",
        description="always fails", fields=("boom_value",),
    )
    def _boom(part, piece):
        raise RuntimeError("expected")

    try:
        piece = Piece(source_path="x.mid", source_format="midi", parts=[Part(index=0)])
        out = base.extract_part(piece.parts[0], piece)
        assert out["boom_value"] is None
        assert "boom" in out["_errors"]
    finally:
        base._REGISTRY.pop("boom")

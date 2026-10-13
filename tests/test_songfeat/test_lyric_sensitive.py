import pytest

from songfeat.features.lyrics import sensitive
from songfeat.features.lyrics.questions import Answer, Kind


def test_there_are_thirteen_subjects_and_thirty_nine_columns():
    assert len(sensitive.SUBJECTS) == 13
    assert len(sensitive.SENSITIVE_FIELDS) == 39
    assert len(sensitive.QUESTIONS) == 39


def test_each_subject_carries_presence_centrality_and_first_person():
    columns = set(sensitive.SENSITIVE_FIELDS)
    assert "sensitive_loss_of_parent" in columns
    assert "sensitive_loss_of_parent_centrality" in columns
    assert "sensitive_loss_of_parent_first_person" in columns


def test_centrality_is_a_score_and_presence_is_a_noul():
    by_id = {question.id: question for question in sensitive.QUESTIONS}
    assert by_id["sensitive_loss_of_parent"].kind is Kind.NOUL
    assert by_id["sensitive_loss_of_parent_centrality"].kind is Kind.SCORE
    assert by_id["sensitive_loss_of_parent_centrality"].levels == 6


def test_there_is_no_composite_column_anywhere_in_the_axis():
    """Sensitivity is a relation between a song and ONE student. Any
    aggregate would be pretending to know something about the student,
    and nothing about a student may enter this database."""
    banned = ("score", "total", "sum", "index", "overall", "composite", "max")
    offenders = [
        field for field in sensitive.SENSITIVE_FIELDS
        if any(word in field for word in banned)
    ]
    assert offenders == []


def test_a_passing_mention_and_an_elegy_are_distinguishable():
    passing = sensitive.columns_from({
        "sensitive_loss_of_parent": Answer("sensitive_loss_of_parent", probability=0.82),
        "sensitive_loss_of_parent_centrality": Answer("sensitive_loss_of_parent_centrality", score=1.0),
    })
    elegy = sensitive.columns_from({
        "sensitive_loss_of_parent": Answer("sensitive_loss_of_parent", probability=0.97),
        "sensitive_loss_of_parent_centrality": Answer("sensitive_loss_of_parent_centrality", score=5.0),
    })
    assert passing["sensitive_loss_of_parent_centrality"] == 1.0
    assert elegy["sensitive_loss_of_parent_centrality"] == 5.0


def test_unasked_subjects_are_null_not_zero():
    out = sensitive.columns_from({})
    for field in sensitive.SENSITIVE_FIELDS:
        assert out[field] is None, field

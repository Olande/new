import pytest

from app.evaluation.metrics import (
    expected_job_id_of,
    is_matching_example,
    per_query_metrics,
    query_style_of,
)
from app.evaluation.run_eval import relative_drop


class MockExample:
    def __init__(self, id, metadata=None, inputs=None, outputs=None):
        self.id = id
        self.metadata = metadata or {}
        self.inputs = inputs or {}
        self.outputs = outputs or {}


def test_query_style_of():
    # Style in metadata
    ex1 = MockExample("1", metadata={"query_style": "paraphrase"})
    assert query_style_of(ex1) == "paraphrase"

    # Style in inputs fallback
    ex2 = MockExample("2", inputs={"query_style": "exact_terms"})
    assert query_style_of(ex2) == "exact_terms"

    # Unknown style
    ex3 = MockExample("3")
    assert query_style_of(ex3) == "unknown"


def test_expected_job_id_of():
    # Valid job id
    ex1 = MockExample("1", outputs={"expected_job_id": "123"})
    assert expected_job_id_of(ex1) == "123"

    # None expected job id
    ex2 = MockExample("2", outputs={"expected_job_id": None})
    assert expected_job_id_of(ex2) is None

    # Empty expected job id
    ex3 = MockExample("3", outputs={"expected_job_id": ""})
    assert expected_job_id_of(ex3) is None

    # "none" expected job id
    ex4 = MockExample("4", outputs={"expected_job_id": "None"})
    assert expected_job_id_of(ex4) is None


def test_is_matching_example():
    # Matching style with expected job id
    ex1 = MockExample(
        "1", metadata={"query_style": "exact_terms"}, outputs={"expected_job_id": "123"}
    )
    assert is_matching_example(ex1) is True

    # Matching style without expected job id
    ex2 = MockExample(
        "2", metadata={"query_style": "exact_terms"}, outputs={"expected_job_id": None}
    )
    assert is_matching_example(ex2) is False

    # no_match style
    ex3 = MockExample(
        "3", metadata={"query_style": "no_match"}, outputs={"expected_job_id": None}
    )
    assert is_matching_example(ex3) is False

    # Unknown style with expected job id
    ex4 = MockExample(
        "4",
        metadata={"query_style": "unknown_style"},
        outputs={"expected_job_id": "456"},
    )
    assert is_matching_example(ex4) is True


def test_per_query_metrics():
    # Normal matching result
    metrics = per_query_metrics(
        qid="q1", expected_job_id="job_abc", ranked_job_ids=["job_xyz", "job_abc"]
    )
    assert metrics is not None
    assert "nDCG@10" in metrics
    assert "RR" in metrics
    # Since expected job is at rank 2 (index 1), Reciprocal Rank is 1/2 = 0.5
    assert metrics["RR"] == 0.5

    # Target not found in ranking
    metrics_not_found = per_query_metrics(
        qid="q2", expected_job_id="job_abc", ranked_job_ids=["job_xyz"]
    )
    assert metrics_not_found is not None
    assert metrics_not_found["RR"] == 0.0
    assert metrics_not_found["nDCG@10"] == 0.0

    # No expected job ID (no_match) returns None
    assert per_query_metrics(qid="q3", expected_job_id=None, ranked_job_ids=[]) is None


def test_relative_drop():
    assert relative_drop(0.8, 0.6) == pytest.approx(0.25)
    assert relative_drop(0.0, 0.5) is None
    assert relative_drop(-0.1, 0.2) is None
    assert relative_drop(1.0, 1.0) == 0.0

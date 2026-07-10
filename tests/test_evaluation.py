"""Unit tests for the CareerPilot evaluation harness.

Tests are designed to be runnable without a database or LangSmith connection.
All DB-dependent code paths are tested via mocking or by isolating the pure
computation functions.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.constants import MATCHING_STYLES, NO_MATCH_STYLE
from app.evaluation.metrics import (
    expected_job_id_of,
    is_matching_example,
    per_query_metrics,
    query_style_of,
)
from app.evaluation.run_eval import check_retrieval_regression, relative_drop

# ---------------------------------------------------------------------------
# Fixture / helpers
# ---------------------------------------------------------------------------


class MockExample:
    def __init__(self, example_id, metadata=None, inputs=None, outputs=None):
        self.id = example_id
        self.metadata = metadata or {}
        self.inputs = inputs or {}
        self.outputs = outputs or {}


class MockProject:
    def __init__(self, name, start_time=None, created_at=None):
        self.name = name
        self.start_time = start_time
        self.created_at = created_at or "2024-01-01T00:00:00Z"


class MockDataset:
    def __init__(self, dataset_id="ds-1"):
        self.id = dataset_id


# ---------------------------------------------------------------------------
# T003 — constants
# ---------------------------------------------------------------------------


def test_constants_exported():
    """Shared constants are importable from constants module."""
    assert "exact_terms" in MATCHING_STYLES
    assert "paraphrase" in MATCHING_STYLES
    assert "distractor" in MATCHING_STYLES
    assert NO_MATCH_STYLE == "no_match"


# ---------------------------------------------------------------------------
# T003 — query_style_of
# ---------------------------------------------------------------------------


def test_query_style_of():
    ex1 = MockExample("1", metadata={"query_style": "paraphrase"})
    assert query_style_of(ex1) == "paraphrase"

    ex2 = MockExample("2", inputs={"query_style": "exact_terms"})
    assert query_style_of(ex2) == "exact_terms"

    ex3 = MockExample("3")
    assert query_style_of(ex3) == "unknown"


# ---------------------------------------------------------------------------
# T003 — expected_job_id_of
# ---------------------------------------------------------------------------


def test_expected_job_id_of():
    assert (
        expected_job_id_of(MockExample("1", outputs={"expected_job_id": "123"}))
        == "123"
    )
    assert (
        expected_job_id_of(MockExample("2", outputs={"expected_job_id": None})) is None
    )
    assert expected_job_id_of(MockExample("3", outputs={"expected_job_id": ""})) is None
    assert (
        expected_job_id_of(MockExample("4", outputs={"expected_job_id": "None"}))
        is None
    )


# ---------------------------------------------------------------------------
# T003 — is_matching_example
# ---------------------------------------------------------------------------


def test_is_matching_example():
    ex_match = MockExample(
        "1", metadata={"query_style": "exact_terms"}, outputs={"expected_job_id": "123"}
    )
    assert is_matching_example(ex_match) is True

    ex_no_id = MockExample(
        "2", metadata={"query_style": "exact_terms"}, outputs={"expected_job_id": None}
    )
    assert is_matching_example(ex_no_id) is False

    ex_no_match = MockExample(
        "3", metadata={"query_style": "no_match"}, outputs={"expected_job_id": None}
    )
    assert is_matching_example(ex_no_match) is False

    ex_unknown = MockExample(
        "4",
        metadata={"query_style": "unknown_style"},
        outputs={"expected_job_id": "456"},
    )
    assert is_matching_example(ex_unknown) is True


# ---------------------------------------------------------------------------
# T003 — per_query_metrics
# ---------------------------------------------------------------------------


def test_per_query_metrics():
    m = per_query_metrics(
        qid="q1", expected_job_id="job_abc", ranked_job_ids=["job_xyz", "job_abc"]
    )
    assert m is not None
    assert "nDCG@10" in m
    assert "RR" in m
    # Expected at rank 2 → RR = 0.5
    assert m["RR"] == pytest.approx(0.5)

    m_miss = per_query_metrics(
        qid="q2", expected_job_id="job_abc", ranked_job_ids=["job_xyz"]
    )
    assert m_miss is not None
    assert m_miss["RR"] == 0.0
    assert m_miss["nDCG@10"] == 0.0

    assert per_query_metrics(qid="q3", expected_job_id=None, ranked_job_ids=[]) is None


# ---------------------------------------------------------------------------
# T003 / T004 — relative_drop
# ---------------------------------------------------------------------------


def test_relative_drop():
    assert relative_drop(0.8, 0.6) == pytest.approx(0.25)
    assert relative_drop(0.0, 0.5) is None
    assert relative_drop(-0.1, 0.2) is None
    assert relative_drop(1.0, 1.0) == 0.0


# ---------------------------------------------------------------------------
# T004 — check_retrieval_regression (mocked LangSmith client)
# ---------------------------------------------------------------------------


def _make_feedback(key: str, score: float):
    fb = MagicMock()
    fb.key = key
    fb.score = score
    return fb


def test_regression_no_dataset():
    """No dataset → no regression flagged."""
    client = MagicMock()
    client.list_datasets.return_value = iter([])
    assert check_retrieval_regression(client, "run-2") is False


def test_regression_no_prior_experiment():
    """Only one experiment exists → no regression possible."""
    client = MagicMock()
    client.list_datasets.return_value = iter([MockDataset()])
    client.list_projects.return_value = [MockProject("run-1")]
    assert check_retrieval_regression(client, "run-1") is False


def test_regression_current_project_missing():
    """Current project name absent from experiments → skip gracefully."""
    client = MagicMock()
    client.list_datasets.return_value = iter([MockDataset()])
    client.list_projects.return_value = [MockProject("run-old")]
    assert check_retrieval_regression(client, "run-new") is False


def test_regression_detected():
    """Significant drop in ndcg_at_10 triggers regression flag."""
    client = MagicMock()
    client.list_datasets.return_value = iter([MockDataset()])
    # Two projects; sorted newest-first by created_at
    client.list_projects.return_value = [
        MockProject("run-new", created_at="2024-02-01"),
        MockProject("run-old", created_at="2024-01-01"),
    ]
    # Mock runs — we only care about feedback scores
    client.list_runs.return_value = [MagicMock(id="r1")]

    def _feedback_side(run_ids, **_):
        # run-new scored 0.5 for ndcg; run-old scored 0.8 → 37.5% drop > 5% threshold
        return iter([_make_feedback("ndcg_at_10", 0.5), _make_feedback("mrr", 0.75)])

    client.list_feedback.side_effect = _feedback_side

    # For run-old use higher scores so the drop is detected
    def _runs_side(project_name=None, **_):
        return [MagicMock(id="r1")]

    client.list_runs.side_effect = _runs_side

    # Patch _feedback_avg to return controlled values
    with patch("app.evaluation.run_eval._feedback_avg") as mock_avg:
        mock_avg.side_effect = [
            # First call: current (run-new) ndcg_at_10
            0.5,
            # Second call: prior (run-old) ndcg_at_10
            0.8,
            # Third call: current (run-new) mrr
            0.75,
            # Fourth call: prior (run-old) mrr
            0.76,
        ]
        result = check_retrieval_regression(client, "run-new")

    assert result is True  # ndcg drop (37.5%) exceeds 5% threshold


def test_no_regression_within_threshold():
    """Tiny metric drop within threshold → no regression."""
    client = MagicMock()
    client.list_datasets.return_value = iter([MockDataset()])
    client.list_projects.return_value = [
        MockProject("run-new", created_at="2024-02-01"),
        MockProject("run-old", created_at="2024-01-01"),
    ]

    with patch("app.evaluation.run_eval._feedback_avg") as mock_avg:
        # <1% drop on both metrics
        mock_avg.side_effect = [0.799, 0.800, 0.699, 0.700]
        result = check_retrieval_regression(client, "run-new")

    assert result is False


# ---------------------------------------------------------------------------
# T007 — Typer CLI contract tests
# ---------------------------------------------------------------------------


def test_typer_cli_help():
    """Typer app's --help output lists evaluate and optimize subcommands."""
    from typer.testing import CliRunner

    from app.evaluation.run_local import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "evaluate" in result.output
    assert "optimize" in result.output


def test_typer_evaluate_signature():
    """evaluate command has expected parameter names."""
    from inspect import signature

    from app.evaluation.run_local import evaluate

    params = set(signature(evaluate).parameters)
    assert "bm25" in params
    assert "vector" in params
    assert "threshold" in params
    assert "limit" in params
    assert "per_query" in params
    assert "as_json" in params


def test_typer_optimize_signature():
    """optimize command has n_trials and limit parameters."""
    from inspect import signature

    from app.evaluation.run_local import optimize

    params = set(signature(optimize).parameters)
    assert "n_trials" in params
    assert "limit" in params

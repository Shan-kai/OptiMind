"""Tests for solver backend abstraction layer."""

from typing import Any

import pytest

from opti_mind.data.models import OptimizationInstance
from opti_mind.knowledge.models import ProblemSpecification
from opti_mind.knowledge.retriever import KnowledgeRetriever
from opti_mind.modeling.generator import IRGenerator
from opti_mind.modeling.ir_models import (
    IRConstraint,
    IRExpression,
    IRExpressionTerm,
    IRModel,
    IRSet,
    IRVariable,
)
from opti_mind.solver.backends import CplexBackend, HighsBackend, MockBackend, SolverBackendRegistry
from opti_mind.solver.backends.base import SolverBackend


class DummyBackend(SolverBackend):
    """Test-only backend for registry assertions."""

    name = "dummy"

    @classmethod
    def available(cls) -> bool:
        return True

    def solve(self, ir: IRModel) -> dict[str, Any]:
        return {"status": "dummy", "objective_value": 0.0, "variables": {}}


def test_registry_register_and_get() -> None:
    """Backends can be registered and retrieved by name."""
    registry = SolverBackendRegistry()
    registry.register(DummyBackend)

    assert "dummy" in registry.list_registered()
    assert registry.get("dummy") is DummyBackend
    assert registry.get("DUMMY") is DummyBackend  # case-insensitive lookup


def test_registry_get_unknown_raises() -> None:
    """Requesting an unregistered backend raises ValueError."""
    registry = SolverBackendRegistry()
    with pytest.raises(ValueError, match="Unknown solver backend"):
        registry.get("nonexistent")


def test_registry_list_available() -> None:
    """list_available returns only backends reporting availability."""
    registry = SolverBackendRegistry()
    registry.register(DummyBackend)
    registry.register(MockBackend)

    available = registry.list_available()
    assert "dummy" in available
    assert "mock" in available


def test_mock_backend_solve_scalar_variable() -> None:
    """MockBackend returns 0.0 for scalar variables and dual info."""
    ir = IRModel(
        problem_type="test",
        variables=[IRVariable(name="z", domain="continuous")],
        constraints=[IRConstraint(name="demand", expr="z", sense="ge", rhs="1")],
    )
    result = MockBackend().solve(ir)

    assert result["status"] == "mock"
    assert result["objective_value"] == 0.0
    assert result["variables"] == {"z": 0.0}
    assert result["dual_values"] == {"demand": 0.0}
    assert result["reduced_costs"] == {"z": 0.0}
    assert result["constraint_values"] == {"demand": 0.0}


def test_mock_backend_solve_indexed_variable() -> None:
    """MockBackend expands indexed variables over their sets."""
    ir = IRModel(
        problem_type="test",
        sets=[IRSet(name="I", members=["a", "b"])],
        variables=[IRVariable(name="x", domain="continuous", sets=["I"])],
    )
    result = MockBackend().solve(ir)

    assert result["status"] == "mock"
    assert result["variables"]["x"] == {"a": 0.0, "b": 0.0}


def test_cplex_backend_available_returns_bool_without_raising() -> None:
    """CplexBackend.available() returns a bool and never propagates import errors."""
    available = CplexBackend.available()
    assert isinstance(available, bool)


def test_highs_backend_available_returns_bool() -> None:
    """HighsBackend.available() returns a bool and never propagates import errors."""
    available = HighsBackend.available()
    assert isinstance(available, bool)


@pytest.mark.skipif(not HighsBackend.available(), reason="highspy not available")
def test_highs_backend_solve_mock_like() -> None:
    """HighsBackend solves a tiny LP and returns the expected solution shape."""
    ir = IRModel(
        problem_type="test",
        sets=[IRSet(name="I", members=["a", "b"])],
        variables=[IRVariable(name="x", domain="continuous", sets=["I"])],
    )
    result = HighsBackend().solve(ir)

    assert result["status"] in ("optimal", "feasible")
    assert result["objective_value"] is not None
    assert "x" in result["variables"]
    assert result["variables"]["x"] == {"a": 0.0, "b": 0.0}


def _make_tiny_lp_ir() -> IRModel:
    """Build a tiny LP with one binding constraint for dual-value checks."""
    return IRModel(
        problem_type="test",
        variables=[
            IRVariable(name="x", domain="continuous"),
            IRVariable(name="y", domain="continuous"),
        ],
        objective=IRExpression(
            terms=[
                IRExpressionTerm(var="x", coef="1"),
                IRExpressionTerm(var="y", coef="1"),
            ]
        ),
        sense="minimize",
        constraints=[IRConstraint(name="demand", expr="x", sense="ge", rhs="1")],
    )


@pytest.mark.skipif(not HighsBackend.available(), reason="highspy not available")
def test_highs_backend_returns_dual_info() -> None:
    """HighsBackend returns non-empty dual_values with at least one non-zero value."""
    ir = _make_tiny_lp_ir()
    result = HighsBackend().solve(ir)

    assert result["status"] == "optimal"
    assert result["dual_values"]
    assert any(v != 0 for v in result["dual_values"].values())
    assert "demand" in result["dual_values"]
    assert result["constraint_values"]["demand"] == pytest.approx(1.0)
    assert result["reduced_costs"]["x"] == pytest.approx(0.0)
    assert result["reduced_costs"]["y"] == pytest.approx(1.0)


def _make_knapsack_ir() -> IRModel:
    """Build the standard tiny knapsack IR used across backend tests."""
    knowledge = KnowledgeRetriever().retrieve(
        ProblemSpecification(problem_type="knapsack", available_fields=["v", "w", "C"])
    )
    instance = OptimizationInstance(
        problem_type="knapsack",
        sets={"I": ["i1", "i2", "i3"]},
        parameters={
            "v": {"i1": 5.0, "i2": 7.0, "i3": 4.0},
            "w": {"i1": 2.0, "i2": 3.0, "i3": 6.0},
            "C": 10.0,
        },
        meta={"dataset_id": "test"},
    )
    return IRGenerator().generate(knowledge, instance)


@pytest.mark.skipif(not HighsBackend.available(), reason="highspy not available")
def test_highs_backend_solves_knapsack() -> None:
    """HiGBackend solves a tiny 0/1 knapsack with an empty-scope sum constraint."""
    ir = _make_knapsack_ir()
    result = HighsBackend().solve(ir)

    assert result["status"] == "optimal"
    assert result["objective_value"] == 12.0
    selected = {k for k, v in result["variables"]["x_i"].items() if v > 0.5}
    assert selected == {"i1", "i2"}

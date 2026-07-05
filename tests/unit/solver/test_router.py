"""Tests for SolverRouter and adapters."""

import os

import pytest

from opti_mind.core.exceptions import SolverError
from opti_mind.data.models import OptimizationInstance
from opti_mind.knowledge.models import ProblemSpecification
from opti_mind.knowledge.retriever import KnowledgeRetriever
from opti_mind.modeling.generator import IRGenerator
from opti_mind.ontology.models import ProblemType
from opti_mind.solver.backends import HighsBackend, MockBackend, SolverBackendRegistry
from opti_mind.solver.router import SolverRouter


def _make_ir():
    knowledge = KnowledgeRetriever().retrieve(
        ProblemSpecification(
            problem_type=ProblemType.FACILITY_LOCATION,
            available_fields=["demand", "fixed_cost", "transport_cost"],
        )
    )
    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1", "c2"], "J": ["f1", "f2"]},
        parameters={
            "d": {"c1": 10, "c2": 20},
            "f": {"f1": 50, "f2": 80},
            "Q": {"f1": 100, "f2": 120},
            "c": {"c1": {"f1": 3.0, "f2": 4.0}, "c2": {"f1": 2.0, "f2": 5.0}},
        },
        meta={"dataset_id": "test"},
    )
    return IRGenerator().generate(knowledge, instance)


def test_mock_solver_returns_zero_solution():
    """MockSolver returns all-zero solutions."""
    ir = _make_ir()
    result = MockBackend().solve(ir)
    assert result["status"] == "mock"
    assert result["objective_value"] == 0.0
    assert "x_ij" in result["variables"]
    assert "y_j" in result["variables"]


def test_mock_solver_handles_scalar_variable():
    """MockBackend handles scalar (non-indexed) variables."""
    from opti_mind.modeling.ir_models import IRModel, IRVariable

    ir = IRModel(
        problem_type="test",
        variables=[IRVariable(name="z", domain="continuous")],
    )
    result = MockBackend().solve(ir)
    assert result["variables"]["z"] == 0.0


def test_mock_solver_handles_all_seven_problem_types():
    """MockBackend works with IRs for all 7 problem types."""
    from opti_mind.ontology.repository import OntologyRepository

    repo = OntologyRepository()
    gen = IRGenerator()
    retriever = KnowledgeRetriever()
    for pt in repo.list_types():
        knowledge = retriever.retrieve(ProblemSpecification(problem_type=pt, available_fields=[]))
        instance = OptimizationInstance(
            problem_type=pt.value,
            sets={"I": [0, 1], "J": [0, 1], "T": [0, 1]},
            parameters={},
            meta={},
        )
        ir = gen.generate(knowledge, instance)
        result = MockBackend().solve(ir)
        assert result["status"] == "mock"
        assert len(result["variables"]) > 0


def test_router_with_mock_backend():
    """SolverRouter uses MockSolver when backend='mock'."""
    os.environ["OPTI_MIND_SOLVER_BACKEND"] = "mock"
    try:
        # Clear the lru_cache so Settings picks up the env var
        from opti_mind.config import get_settings

        get_settings.cache_clear()
        ir = _make_ir()
        router = SolverRouter()
        result = router.solve(ir)
        assert result["status"] == "mock"
    finally:
        os.environ.pop("OPTI_MIND_SOLVER_BACKEND", None)
        get_settings.cache_clear()


@pytest.mark.skipif(not HighsBackend.available(), reason="highspy not available")
def test_router_with_highs_backend():
    """SolverRouter can select and solve with the highs backend."""
    os.environ["OPTI_MIND_SOLVER_BACKEND"] = "highs"
    try:
        from opti_mind.config import get_settings

        get_settings.cache_clear()
        ir = _make_ir()
        router = SolverRouter()
        result = router.solve(ir)
        assert result["status"] in ("optimal", "feasible")
        assert result["objective_value"] is not None
        assert "x_ij" in result["variables"]
        assert "y_j" in result["variables"]
    finally:
        os.environ.pop("OPTI_MIND_SOLVER_BACKEND", None)
        get_settings.cache_clear()


def test_router_unknown_backend_raises():
    """SolverRouter raises ValueError for unknown backend."""
    import os

    os.environ["OPTI_MIND_SOLVER_BACKEND"] = "nonexistent"
    try:
        from opti_mind.config import get_settings

        get_settings.cache_clear()
        router = SolverRouter()
        with pytest.raises(ValueError, match="Unknown solver backend"):
            router.solve(_make_ir())
    finally:
        os.environ.pop("OPTI_MIND_SOLVER_BACKEND", None)
        get_settings.cache_clear()


def test_router_uses_injected_registry():
    """SolverRouter can be given a custom registry for testing."""
    os.environ["OPTI_MIND_SOLVER_BACKEND"] = "mock"
    try:
        from opti_mind.config import get_settings

        get_settings.cache_clear()
        registry = SolverBackendRegistry()
        registry.register(MockBackend)

        router = SolverRouter(registry=registry)
        result = router.solve(_make_ir())
        assert result["status"] == "mock"
    finally:
        os.environ.pop("OPTI_MIND_SOLVER_BACKEND", None)
        get_settings.cache_clear()


def test_router_wraps_backend_exception_as_solver_error():
    """SolverRouter wraps backend solve exceptions in SolverError."""

    class ExplodingBackend(MockBackend):
        name = "exploding"

        def solve(self, ir):
            raise RuntimeError("boom in backend")

    os.environ["OPTI_MIND_SOLVER_BACKEND"] = "exploding"
    try:
        from opti_mind.config import get_settings

        get_settings.cache_clear()
        registry = SolverBackendRegistry()
        registry.register(ExplodingBackend)
        router = SolverRouter(registry=registry)
        with pytest.raises(SolverError, match="Solver failed"):
            router.solve(_make_ir())
    finally:
        os.environ.pop("OPTI_MIND_SOLVER_BACKEND", None)
        get_settings.cache_clear()


def test_router_returns_solver_unavailable_when_backend_not_available():
    """SolverRouter returns a structured dict when the backend is not available."""

    class UnavailableBackend(MockBackend):
        name = "unavailable"

        @classmethod
        def available(cls) -> bool:
            return False

    os.environ["OPTI_MIND_SOLVER_BACKEND"] = "unavailable"
    try:
        from opti_mind.config import get_settings

        get_settings.cache_clear()
        registry = SolverBackendRegistry()
        registry.register(UnavailableBackend)
        router = SolverRouter(registry=registry)
        result = router.solve(_make_ir())
        assert result["status"] == "solver_unavailable"
        assert result["objective_value"] is None
        assert result["variables"] == {}
        assert "CPLEX" in result["error"] or "mock" in result["error"]
    finally:
        os.environ.pop("OPTI_MIND_SOLVER_BACKEND", None)
        get_settings.cache_clear()


def test_router_returns_solver_unavailable_on_runtime_error():
    """SolverRouter returns a structured dict for CPLEX/license-like RuntimeError."""

    class LicenseFailingBackend(MockBackend):
        name = "license_failing"

        def solve(self, ir):
            raise RuntimeError("CPLEX license not found")

    os.environ["OPTI_MIND_SOLVER_BACKEND"] = "license_failing"
    try:
        from opti_mind.config import get_settings

        get_settings.cache_clear()
        registry = SolverBackendRegistry()
        registry.register(LicenseFailingBackend)
        router = SolverRouter(registry=registry)
        result = router.solve(_make_ir())
        assert result["status"] == "solver_unavailable"
        assert result["objective_value"] is None
        assert result["variables"] == {}
        assert result["error"]
    finally:
        os.environ.pop("OPTI_MIND_SOLVER_BACKEND", None)
        get_settings.cache_clear()


def test_router_solve_dict_returns_solver_unavailable():
    """SolverRouter.solve_dict also returns the structured unavailable dict."""

    class UnavailableBackend(MockBackend):
        name = "unavailable_dict"

        @classmethod
        def available(cls) -> bool:
            return False

    os.environ["OPTI_MIND_SOLVER_BACKEND"] = "unavailable_dict"
    try:
        from opti_mind.config import get_settings

        get_settings.cache_clear()
        registry = SolverBackendRegistry()
        registry.register(UnavailableBackend)
        router = SolverRouter(registry=registry)
        ir = _make_ir()
        result = router.solve_dict(ir.model_dump())
        assert result["status"] == "solver_unavailable"
        assert "error" in result
    finally:
        os.environ.pop("OPTI_MIND_SOLVER_BACKEND", None)
        get_settings.cache_clear()


@pytest.mark.solver
def test_cplex_solver_solves_simple_model():
    """CPLEX adapter can solve a simple LP (requires CPLEX runtime).

    Marked with .solver — skipped in CI without a CPLEX license.
    """
    import os

    os.environ["OPTI_MIND_SOLVER_BACKEND"] = "cplex"
    os.environ["OPTI_MIND_CPLEX_BIN_DIR"] = "D:\\cplex\\bin\\x64_win64"
    try:
        from opti_mind.config import get_settings

        get_settings.cache_clear()
        from opti_mind.solver.backends import CplexBackend

        ir = _make_ir()
        result = CplexBackend().solve(ir)
        assert result["status"] in ("optimal", "feasible")
        assert result["objective_value"] is not None
    finally:
        os.environ.pop("OPTI_MIND_SOLVER_BACKEND", None)
        os.environ.pop("OPTI_MIND_CPLEX_BIN_DIR", None)
        get_settings.cache_clear()

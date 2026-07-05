"""Tests for the ScenarioEngine what-if analysis."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from opti_mind.data.service import DataService
from opti_mind.decision.models import ScenarioComparison
from opti_mind.decision.scenario import ScenarioEngine
from opti_mind.decision.service import DecisionService
from opti_mind.knowledge.models import ProblemSpecification
from opti_mind.knowledge.retriever import KnowledgeRetriever
from opti_mind.modeling.generator import IRGenerator
from opti_mind.modeling.ir_models import IRModel
from opti_mind.ontology.models import ProblemType
from opti_mind.solver.backends import HighsBackend
from opti_mind.solver.router import SolverRouter


@pytest.fixture
def highs_router(monkeypatch: Any) -> SolverRouter:
    """Provide a SolverRouter configured to use the HiGHS backend."""
    if not HighsBackend.available():
        pytest.skip("highspy not available")

    monkeypatch.setenv("OPTI_MIND_SOLVER_BACKEND", "highs")
    from opti_mind.config import get_settings

    get_settings.cache_clear()
    router = SolverRouter()
    yield router
    get_settings.cache_clear()


def _make_facility_ir() -> IRModel:
    """Build a facility-location IR from the CSV fixture."""
    instance = DataService().build_instance_from_file("tests/fixtures/facility_location.csv")
    knowledge = KnowledgeRetriever().retrieve(
        ProblemSpecification(problem_type=ProblemType.FACILITY_LOCATION, available_fields=[])
    )
    return IRGenerator().generate(knowledge, instance)


def _make_assignment_ir() -> IRModel:
    """Build an assignment-problem IR from the CSV fixture."""
    instance = DataService().build_instance_from_file("tests/fixtures/assignment.csv")
    knowledge = KnowledgeRetriever().retrieve(
        ProblemSpecification(problem_type=ProblemType.ASSIGNMENT, available_fields=[])
    )
    return IRGenerator().generate(knowledge, instance)


class TestScenarioEngineInjection:
    def test_accepts_solver_router(self, highs_router: SolverRouter) -> None:
        """ScenarioEngine can be constructed with an injected SolverRouter."""
        engine = ScenarioEngine(highs_router)
        comparisons = engine.compare({"objective_value": 1.0}, None)
        assert comparisons == []

    def test_default_solver_router_when_none_provided(self) -> None:
        """ScenarioEngine falls back to a default SolverRouter."""
        engine = ScenarioEngine()
        assert engine._solver_router is not None


class TestScenarioEngineApplyScenario:
    def test_modifies_instance_parameters(self, highs_router: SolverRouter) -> None:
        """_apply_scenario updates the copied instance parameters."""
        engine = ScenarioEngine(highs_router)
        ir = _make_facility_ir()
        modified = engine._apply_scenario(ir, {"changes": ["c_ij *= 0.9"]})
        assert modified is not None
        assert modified is not ir
        original = ir.meta["instance_parameters"]["c_ij"]["c1"]["f1"]
        updated = modified.meta["instance_parameters"]["c_ij"]["c1"]["f1"]
        assert updated == pytest.approx(original * 0.9)
        # Original IR must remain unchanged.
        assert ir.meta["instance_parameters"]["c_ij"]["c1"]["f1"] == original

    def test_applies_change_to_base_and_aliased_keys(self, highs_router: SolverRouter) -> None:
        """Changing a base key also updates aliased canonical keys."""
        engine = ScenarioEngine(highs_router)
        ir = _make_facility_ir()
        modified = engine._apply_scenario(ir, {"changes": ["c *= 0.5"]})
        assert modified is not None
        assert modified.meta["instance_parameters"]["c"]["c1"]["f1"] == pytest.approx(
            ir.meta["instance_parameters"]["c_ij"]["c1"]["f1"] * 0.5
        )
        assert modified.meta["instance_parameters"]["c_ij"]["c1"]["f1"] == pytest.approx(
            ir.meta["instance_parameters"]["c_ij"]["c1"]["f1"] * 0.5
        )

    def test_single_element_change_comma_form(self, highs_router: SolverRouter) -> None:
        """Changing a single matrix element with comma indexing updates only that element."""
        engine = ScenarioEngine(highs_router)
        ir = _make_assignment_ir()
        modified = engine._apply_scenario(ir, {"changes": ["c_ij[a1,t1] -= 10"]})
        assert modified is not None
        assert modified is not ir
        assert modified.meta["instance_parameters"]["c_ij"]["a1"]["t1"] == pytest.approx(
            ir.meta["instance_parameters"]["c_ij"]["a1"]["t1"] - 10
        )
        # Other elements must remain unchanged.
        assert modified.meta["instance_parameters"]["c_ij"]["a1"]["t2"] == pytest.approx(
            ir.meta["instance_parameters"]["c_ij"]["a1"]["t2"]
        )
        assert modified.meta["instance_parameters"]["c_ij"]["a2"]["t1"] == pytest.approx(
            ir.meta["instance_parameters"]["c_ij"]["a2"]["t1"]
        )

    def test_single_element_change_nested_bracket_form(self, highs_router: SolverRouter) -> None:
        """Changing a single matrix element with nested-bracket indexing works."""
        engine = ScenarioEngine(highs_router)
        ir = _make_assignment_ir()
        modified = engine._apply_scenario(ir, {"changes": ["c_ij[a1][t1] -= 10"]})
        assert modified is not None
        assert modified.meta["instance_parameters"]["c_ij"]["a1"]["t1"] == pytest.approx(
            ir.meta["instance_parameters"]["c_ij"]["a1"]["t1"] - 10
        )
        assert modified.meta["instance_parameters"]["c_ij"]["a1"]["t2"] == pytest.approx(
            ir.meta["instance_parameters"]["c_ij"]["a1"]["t2"]
        )


class TestScenarioEngineEstimateDelta:
    def test_cost_change_yields_nonzero_delta(self, highs_router: SolverRouter) -> None:
        """Reducing transport costs changes the re-solved objective."""
        engine = ScenarioEngine(highs_router)
        ir = _make_facility_ir()
        baseline = highs_router.solve(ir)
        baseline_objective = baseline.get("objective_value")
        assert baseline_objective is not None
        scenarios = [{"name": "Reduce transport cost", "changes": ["c_ij *= 0.9"]}]
        comparisons = engine.compare(baseline, ir, scenarios)
        assert len(comparisons) == 1
        comparison = comparisons[0]
        assert comparison.objective_delta is not None
        assert comparison.objective_delta != 0.0
        assert comparison.baseline_objective == pytest.approx(baseline_objective)
        assert comparison.scenario_objective < comparison.baseline_objective

    def test_capacity_change_is_handled_gracefully(self, highs_router: SolverRouter) -> None:
        """The facility-location IR now includes capacity constraints, so changing
        ``Q`` may change the objective. The engine must remain feasible and not crash."""
        engine = ScenarioEngine(highs_router)
        ir = _make_facility_ir()
        baseline = highs_router.solve(ir)
        scenarios = [{"name": "Increase capacity", "changes": ["Q *= 1.2"]}]
        comparisons = engine.compare(baseline, ir, scenarios)
        assert len(comparisons) == 1
        comparison = comparisons[0]
        assert comparison.baseline_objective is not None
        assert comparison.scenario_objective is not None
        assert comparison.objective_delta is not None
        # Relaxing capacity cannot make a minimization problem worse.
        assert comparison.scenario_objective <= comparison.baseline_objective

    def test_invalid_change_string_is_skipped(
        self, highs_router: SolverRouter, caplog: Any
    ) -> None:
        """Unparseable changes are skipped with a warning; valid changes apply."""
        engine = ScenarioEngine(highs_router)
        ir = _make_facility_ir()
        baseline = highs_router.solve(ir)
        scenarios = [
            {
                "name": "Mixed changes",
                "changes": ["not a valid change", "c_ij *= 0.9"],
            }
        ]
        with caplog.at_level(logging.WARNING):
            comparisons = engine.compare(baseline, ir, scenarios)
        assert len(comparisons) == 1
        assert comparisons[0].objective_delta != 0.0
        assert "Could not parse" in caplog.text

    def test_unknown_parameter_key_is_skipped(
        self, highs_router: SolverRouter, caplog: Any
    ) -> None:
        """Changes referencing missing parameters are skipped with a warning."""
        engine = ScenarioEngine(highs_router)
        ir = _make_facility_ir()
        baseline = highs_router.solve(ir)
        scenarios = [{"name": "Unknown param", "changes": ["zzz *= 2"]}]
        with caplog.at_level(logging.WARNING):
            comparisons = engine.compare(baseline, ir, scenarios)
        assert comparisons[0].objective_delta == 0.0
        assert "not found in instance parameters" in caplog.text

    def test_no_ir_returns_zero_delta(self, highs_router: SolverRouter, caplog: Any) -> None:
        """A missing IR yields a zero delta with a warning."""
        engine = ScenarioEngine(highs_router)
        with caplog.at_level(logging.WARNING):
            delta = engine._estimate_delta({"objective_value": 100.0}, None, {})
        assert delta == 0.0
        assert "without an IR model" in caplog.text

    def test_none_baseline_objective_returns_zero(
        self, highs_router: SolverRouter, caplog: Any
    ) -> None:
        """A baseline without an objective value yields a zero delta."""
        engine = ScenarioEngine(highs_router)
        ir = _make_facility_ir()
        with caplog.at_level(logging.WARNING):
            delta = engine._estimate_delta(
                {"objective_value": None}, ir, {"changes": ["c_ij *= 0.9"]}
            )
        assert delta == 0.0
        assert "Baseline objective value unavailable" in caplog.text


class TestDecisionServiceScenarioInjection:
    def test_service_uses_injected_scenario_engine(self, highs_router: SolverRouter) -> None:
        """DecisionService can be constructed with an injected ScenarioEngine."""
        engine = ScenarioEngine(highs_router)
        service = DecisionService(scenario_engine=engine)
        ir = _make_facility_ir()
        baseline = highs_router.solve(ir)
        scenarios = [{"name": "Cost cut", "changes": ["c_ij *= 0.9"]}]
        report = service.analyze(baseline, ir, scenarios)
        assert len(report.scenario_comparisons) == 1
        comparison = report.scenario_comparisons[0]
        assert isinstance(comparison, ScenarioComparison)
        assert comparison.objective_delta != 0.0

    def test_service_backward_compatible(self) -> None:
        """DecisionService works without an explicit ScenarioEngine."""
        service = DecisionService()
        report = service.analyze({"status": "optimal", "objective_value": 42.0})
        assert report.status == "optimal"
        assert report.scenario_comparisons == []

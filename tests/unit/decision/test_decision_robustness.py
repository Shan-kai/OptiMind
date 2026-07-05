"""Robustness tests for the decision intelligence layer with no_solution inputs."""

from __future__ import annotations

from opti_mind.decision.models import AnalysisReport
from opti_mind.decision.scenario import ScenarioEngine
from opti_mind.decision.service import DecisionService


def test_decision_service_analyze_none_returns_no_solution_report() -> None:
    """A None solution must yield a no_solution AnalysisReport with a feasibility risk."""
    service = DecisionService(scenario_engine=ScenarioEngine())
    report = service.analyze(None, ir=None)

    assert isinstance(report, AnalysisReport)
    assert report.status == "no_solution"
    assert any(
        risk.category == "feasibility" and risk.severity == "critical" for risk in report.risk_items
    )


def test_decision_service_analyze_no_solution_status_returns_simplified_report() -> None:
    """A solution dict with status no_solution must produce a simplified report."""
    service = DecisionService(scenario_engine=ScenarioEngine())
    report = service.analyze({"status": "no_solution"}, ir=None)

    assert isinstance(report, AnalysisReport)
    assert report.status == "no_solution"
    assert any(
        risk.category == "feasibility" and risk.severity == "critical" for risk in report.risk_items
    )
    assert report.sensitivity_results == []
    assert report.scenario_comparisons == []


def test_scenario_engine_compare_none_returns_empty() -> None:
    """Comparing against a None baseline must not raise and return an empty list."""
    engine = ScenarioEngine()
    result = engine.compare(None, ir=None, scenarios=[])

    assert result == []

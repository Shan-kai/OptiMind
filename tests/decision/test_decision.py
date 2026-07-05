"""Tests for decision intelligence modules."""

from __future__ import annotations

import pytest

from opti_mind.decision.interpreter import SolutionInterpreter
from opti_mind.decision.models import AnalysisReport
from opti_mind.decision.recommendation import RecommendationEngine
from opti_mind.decision.risk import RiskEvaluator
from opti_mind.decision.scenario import ScenarioEngine
from opti_mind.decision.sensitivity import SensitivityAnalyzer
from opti_mind.decision.service import DecisionService


@pytest.fixture
def mock_solution() -> dict:
    return {
        "status": "optimal",
        "objective_value": 42.0,
        "variables": {
            "x": 1.0,
            "y": {"0": 2.0, "1": 3.0},
        },
    }


@pytest.fixture
def no_solution() -> dict:
    return {
        "status": "no_solution",
        "objective_value": None,
        "variables": {},
    }


class TestSolutionInterpreter:
    def test_interpret_optimal(self, mock_solution: dict) -> None:
        interpreter = SolutionInterpreter()
        report = interpreter.interpret(mock_solution)
        assert report.status == "optimal"
        assert report.objective_value == 42.0
        assert len(report.variable_summaries) == 2
        names = [v.name for v in report.variable_summaries]
        assert "x" in names
        assert "y" in names
        assert report.executive_summary

    def test_interpret_no_solution(self, no_solution: dict) -> None:
        interpreter = SolutionInterpreter()
        report = interpreter.interpret(no_solution)
        assert report.status == "no_solution"
        assert "未找到可行解" in report.executive_summary


class TestSensitivityAnalyzer:
    def test_analyze_empty(self, mock_solution: dict) -> None:
        analyzer = SensitivityAnalyzer()
        results = analyzer.analyze(mock_solution)
        assert results == []


class TestScenarioEngine:
    def test_compare_empty(self, mock_solution: dict) -> None:
        engine = ScenarioEngine()
        comparisons = engine.compare(mock_solution, None)
        assert comparisons == []


class TestRiskEvaluator:
    def test_no_solution_risk(self, no_solution: dict) -> None:
        evaluator = RiskEvaluator()
        risks = evaluator.evaluate(no_solution)
        assert len(risks) == 1
        assert risks[0].severity == "critical"

    def test_optimal_no_risk(self, mock_solution: dict) -> None:
        evaluator = RiskEvaluator()
        risks = evaluator.evaluate(mock_solution)
        assert len(risks) == 0


class TestRecommendationEngine:
    def test_no_solution_recommendation(self, no_solution: dict) -> None:
        engine = RecommendationEngine()
        report = AnalysisReport(status="no_solution")
        recs = engine.generate(report)
        assert len(recs) == 1
        assert recs[0].priority == "high"

    def test_optimal_recommendation(self, mock_solution: dict) -> None:
        engine = RecommendationEngine()
        interpreter = SolutionInterpreter()
        report = interpreter.interpret(mock_solution)
        recs = engine.generate(report)
        assert len(recs) >= 1


class TestDecisionService:
    def test_analyze(self, mock_solution: dict) -> None:
        service = DecisionService()
        report = service.analyze(mock_solution)
        assert report.status == "optimal"
        assert report.objective_value == 42.0
        assert len(report.variable_summaries) == 2

    def test_analyze_no_solution(self, no_solution: dict) -> None:
        service = DecisionService()
        report = service.analyze(no_solution)
        assert report.status == "no_solution"
        assert len(report.risk_items) == 1
        assert len(report.recommendations) == 1

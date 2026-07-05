"""Tests for the decision analysis tool executor."""

from __future__ import annotations

from typing import Any

from opti_mind.chat.decision_tool_executor import DecisionToolExecutor
from opti_mind.decision.models import AnalysisReport, Recommendation, RiskItem


class FakeSensitivityAnalyzer:
    """Stub sensitivity analyzer returning deterministic results."""

    def analyze(self, solution: dict[str, Any], ir: Any | None = None) -> list[dict[str, Any]]:
        del solution, ir
        from opti_mind.decision.models import SensitivityResult

        return [
            SensitivityResult(
                parameter_name="c_ij",
                current_value=1.0,
                shadow_price=2.5,
                interpretation="Cost parameter is binding.",
            ),
            SensitivityResult(
                parameter_name="Q_j",
                current_value=100.0,
                shadow_price=0.0,
                interpretation="Capacity has slack.",
            ),
        ]


class FakeScenarioEngine:
    """Stub scenario engine returning a deterministic comparison."""

    def compare(
        self,
        baseline_solution: dict[str, Any],
        ir: Any | None,
        scenarios: list[dict[str, Any]] | None,
    ) -> list[Any]:
        del baseline_solution, ir
        from opti_mind.decision.models import ScenarioComparison

        name = scenarios[0].get("name", "what-if") if scenarios else "what-if"
        return [
            ScenarioComparison(
                scenario_name=name,
                baseline_objective=42.0,
                scenario_objective=46.2,
                objective_delta=4.2,
                objective_delta_pct=10.0,
                key_changes=scenarios[0].get("changes", []) if scenarios else [],
                recommendation="Consider this scenario.",
            )
        ]


def test_summarize_report_returns_summary() -> None:
    """summarize_report extracts the key sections of an AnalysisReport."""
    report = AnalysisReport(
        status="optimal",
        objective_value=42.0,
        objective_sense="minimize",
        executive_summary="Good solution.",
        recommendations=[
            Recommendation(
                category="cost",
                priority="high",
                title="Reduce fixed costs",
                description="Consider cheaper facilities.",
            )
        ],
        risk_items=[
            RiskItem(
                category="demand",
                severity="medium",
                description="Demand may fluctuate.",
            )
        ],
    )
    executor = DecisionToolExecutor()
    state = {"report": report.model_dump(mode="json")}

    result = executor.execute({"tool": "summarize_report", "input": {}}, state)

    assert result["status"] == "ok"
    assert result["result"]["objective_value"] == 42.0
    assert result["result"]["executive_summary"] == "Good solution."
    assert len(result["result"]["recommendations"]) == 1
    assert len(result["result"]["risk_items"]) == 1


def test_explain_solution_returns_metrics() -> None:
    """explain_solution returns objective value, status, and variable count."""
    executor = DecisionToolExecutor()
    state = {
        "solution": {
            "status": "optimal",
            "objective_value": 42.0,
            "variables": {"x": 1.0, "y": 2.0},
        },
        "report": AnalysisReport(status="optimal").model_dump(mode="json"),
    }

    result = executor.execute({"tool": "explain_solution", "input": {}}, state)

    assert result["status"] == "ok"
    assert result["result"]["objective_value"] == 42.0
    assert result["result"]["status"] == "optimal"
    assert result["result"]["variable_count"] == 2


def test_analyze_sensitivity_filters_by_parameter() -> None:
    """analyze_sensitivity returns all results or filters to one parameter."""
    executor = DecisionToolExecutor(
        sensitivity_analyzer=FakeSensitivityAnalyzer(),
    )
    state = {"solution": {"objective_value": 42.0}}

    result = executor.execute(
        {"tool": "analyze_sensitivity", "input": {"parameter_name": "c_ij"}},
        state,
    )

    assert result["status"] == "ok"
    assert len(result["result"]["results"]) == 1
    assert result["result"]["results"][0]["parameter_name"] == "c_ij"


def test_run_scenario_returns_comparison() -> None:
    """run_scenario converts changes into a ScenarioComparison."""
    executor = DecisionToolExecutor(
        scenario_engine=FakeScenarioEngine(),
    )
    state = {
        "solution": {"objective_value": 42.0},
        "report": AnalysisReport(status="optimal").model_dump(mode="json"),
    }

    result = executor.execute(
        {"tool": "run_scenario", "input": {"changes": ["c_ij *= 1.1"], "name": "increase cost"}},
        state,
    )

    assert result["status"] == "ok"
    comparison = result["result"]["comparison"]
    assert comparison["scenario_name"] == "increase cost"
    assert comparison["objective_delta"] == 4.2


def test_run_scenario_without_solution_errors() -> None:
    """run_scenario returns an error when no solution exists."""
    executor = DecisionToolExecutor()
    state: dict[str, Any] = {}

    result = executor.execute(
        {"tool": "run_scenario", "input": {"changes": ["c_ij *= 1.1"]}},
        state,
    )

    assert result["status"] == "error"
    assert "solution" in result["error"]


def test_ask_user_returns_question() -> None:
    """ask_user returns the question with ask_user flag."""
    executor = DecisionToolExecutor()
    state: dict[str, Any] = {}

    result = executor.execute(
        {"tool": "ask_user", "input": {"question": "Which parameter?"}},
        state,
    )

    assert result["status"] == "ok"
    assert result["ask_user"] is True
    assert result["result"]["question"] == "Which parameter?"

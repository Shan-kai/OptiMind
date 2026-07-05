"""Tool executor for the LLM-driven decision analysis agent.

All tools are read-only or re-solve copies of the model; they never mutate the
original workflow state. Results are returned as JSON-serializable dicts so the
generic ``AgentLoop`` can apply them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from opti_mind.chat.decision_tools import (
    AnalyzeSensitivityInput,
    AskUserInput,
    RunScenarioInput,
)
from opti_mind.decision.models import AnalysisReport
from opti_mind.decision.scenario import ScenarioEngine
from opti_mind.decision.sensitivity import SensitivityAnalyzer
from opti_mind.decision.service import DecisionService
from opti_mind.modeling.ir_models import IRModel
from opti_mind.solver.router import SolverRouter

logger = logging.getLogger(__name__)


class DecisionToolExecutor:
    """Execute tools requested by the decision analysis agent."""

    def __init__(
        self,
        decision_service: DecisionService | None = None,
        scenario_engine: ScenarioEngine | None = None,
        sensitivity_analyzer: SensitivityAnalyzer | None = None,
    ) -> None:
        self.decision_service = decision_service or DecisionService()
        self.scenario_engine = scenario_engine or ScenarioEngine(SolverRouter())
        self.sensitivity_analyzer = sensitivity_analyzer or SensitivityAnalyzer()

    def execute(self, tool_call: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a single decision tool call."""
        tool = tool_call.get("tool", "")
        input_data = tool_call.get("input", {})
        handler: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = getattr(
            self, f"_{tool}", None
        )
        if handler is None:
            return {"status": "error", "error": f"Unknown tool: {tool}"}
        try:
            return handler(input_data, state)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Decision tool %s failed", tool)
            return {"status": "error", "error": f"{tool}: {exc}"}

    def _explain_solution(self, _input: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """Return a compact summary of the solver solution."""
        solution = state.get("solution") or {}
        report_data = state.get("report")
        report = AnalysisReport.model_validate(report_data) if report_data else None

        return {
            "status": "ok",
            "result": {
                "objective_value": solution.get("objective_value"),
                "status": solution.get("status"),
                "variable_count": len(solution.get("variables") or {}),
                "executive_summary": report.executive_summary if report else "",
            },
        }

    def _analyze_sensitivity(
        self, input_data: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        """Run sensitivity analysis for one or all parameters."""
        validated = AnalyzeSensitivityInput.model_validate(input_data)
        solution = state.get("solution") or {}
        ir_data = state.get("verified_ir") or state.get("ir")
        ir = IRModel.model_validate(ir_data) if ir_data else None

        results = self.sensitivity_analyzer.analyze(solution, ir)
        if validated.parameter_name:
            results = [r for r in results if r.parameter_name == validated.parameter_name]

        return {
            "status": "ok",
            "result": {
                "parameter_name": validated.parameter_name,
                "results": [r.model_dump(mode="json") for r in results],
            },
        }

    def _run_scenario(self, input_data: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """Run a what-if scenario by modifying parameters and re-solving."""
        validated = RunScenarioInput.model_validate(input_data)
        solution = state.get("solution")
        ir_data = state.get("verified_ir") or state.get("ir")
        ir = IRModel.model_validate(ir_data) if ir_data else None

        if not solution:
            return {"status": "error", "error": "No solution available to compare against"}

        scenario = {
            "name": validated.name or "what-if",
            "changes": validated.changes,
        }
        comparison = self.scenario_engine.compare(solution, ir, scenarios=[scenario])
        return {
            "status": "ok",
            "result": {
                "scenario": scenario,
                "comparison": comparison[0].model_dump(mode="json") if comparison else None,
            },
        }

    def _summarize_report(self, _input: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """Return a structured summary of the full analysis report."""
        report_data = state.get("report")
        if not report_data:
            return {"status": "error", "error": "No analysis report available"}

        report = AnalysisReport.model_validate(report_data)
        return {
            "status": "ok",
            "result": {
                "status": report.status,
                "objective_value": report.objective_value,
                "objective_sense": report.objective_sense,
                "executive_summary": report.executive_summary,
                "llm_summary": report.llm_summary,
                "recommendations": [r.model_dump(mode="json") for r in report.recommendations],
                "risk_items": [r.model_dump(mode="json") for r in report.risk_items],
                "sensitivity_count": len(report.sensitivity_results),
                "scenario_count": len(report.scenario_comparisons),
            },
        }

    def _ask_user(self, input_data: dict[str, Any], _state: dict[str, Any]) -> dict[str, Any]:
        """Return a question that ends the current turn."""
        validated = AskUserInput.model_validate(input_data)
        return {
            "status": "ok",
            "result": {"question": validated.question},
            "ask_user": True,
        }

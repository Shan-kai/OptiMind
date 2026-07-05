"""Decision service - orchestrates all decision intelligence modules."""

from __future__ import annotations

import logging
from typing import Any

from opti_mind.config import get_settings
from opti_mind.decision.interpreter import SolutionInterpreter
from opti_mind.decision.models import AnalysisReport, RiskItem
from opti_mind.decision.recommendation import RecommendationEngine
from opti_mind.decision.risk import RiskEvaluator
from opti_mind.decision.scenario import ScenarioEngine
from opti_mind.decision.sensitivity import SensitivityAnalyzer
from opti_mind.modeling.ir_models import IRModel
from opti_mind.solver.router import SolverRouter

logger = logging.getLogger(__name__)


class DecisionService:
    """Orchestrate decision intelligence analysis."""

    def __init__(self, scenario_engine: ScenarioEngine | None = None) -> None:
        self._interpreter = SolutionInterpreter()
        self._sensitivity = SensitivityAnalyzer()
        self._scenario = scenario_engine or ScenarioEngine(SolverRouter())
        self._risk = RiskEvaluator()
        self._recommendation = RecommendationEngine()

    def analyze(
        self,
        solution: dict[str, Any],
        ir: IRModel | None = None,
        scenarios: list[dict[str, Any]] | None = None,
        business_goal: str | None = None,
    ) -> AnalysisReport:
        """Run full decision intelligence analysis.

        Args:
            solution: Raw solver output.
            ir: Optional IR model for deeper analysis.
            scenarios: Optional list of what-if scenarios.
            business_goal: Optional natural language business objective.

        Returns:
            Complete AnalysisReport with all insights.
        """
        if solution is None:
            logger.warning("DecisionService received None solution, returning no_solution report")
            return self._no_solution_report(raw_solution={})

        if solution.get("status") == "no_solution":
            logger.warning(
                "DecisionService received no_solution status, returning simplified report"
            )
            return self._no_solution_report(raw_solution=solution)

        # Step 1: Interpret the solution
        report = self._interpreter.interpret(solution, ir)

        # Step 2: Sensitivity analysis
        report.sensitivity_results = self._sensitivity.analyze(solution, ir)

        # Step 3: Scenario comparison
        report.scenario_comparisons = self._scenario.compare(solution, ir, scenarios)

        # Step 4: Risk evaluation
        report.risk_items = self._risk.evaluate(solution, ir)

        # Step 5: Generate recommendations
        report.recommendations = self._recommendation.generate(report)

        # Step 6 (optional): LLM-augmented narrative summary
        if get_settings().llm_decision_analyzer:
            try:
                from opti_mind.decision.llm_analyzer import LLMDecisionAnalyzer

                analyzer = LLMDecisionAnalyzer()
                analyzer.enhance(report, solution, ir, business_goal, scenarios)
            except Exception as exc:  # noqa: BLE001 - LLM must not break report
                logger.warning("LLM decision analysis failed, skipping: %s", exc)

        return report

    def _no_solution_report(self, raw_solution: dict[str, Any]) -> AnalysisReport:
        """Return a minimal AnalysisReport for missing or infeasible solutions."""
        report = AnalysisReport(
            status="no_solution",
            executive_summary="求解器未找到可行解。请检查模型约束与数据。",
            risk_items=[
                RiskItem(
                    category="feasibility",
                    severity="critical",
                    description="未找到可行解。问题可能过约束或数据不一致。",
                    mitigation="检查约束条件、放宽硬性限制或校验数据质量。",
                )
            ],
            raw_solution=raw_solution,
        )
        report.recommendations = self._recommendation.generate(report)
        return report

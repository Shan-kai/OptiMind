"""Solution interpreter - extracts insights from solver output."""

from __future__ import annotations

from typing import Any

from opti_mind.decision.models import (
    AnalysisReport,
    ConstraintStatus,
    VariableSummary,
)
from opti_mind.modeling.ir_models import IRModel


class SolutionInterpreter:
    """Interpret a solver solution and produce human-readable summaries."""

    def interpret(self, solution: dict[str, Any], ir: IRModel | None = None) -> AnalysisReport:
        """Build an initial AnalysisReport from raw solver output."""
        status = solution.get("status", "unknown")
        objective_value = solution.get("objective_value")

        var_summaries = self._summarize_variables(solution.get("variables", {}), ir)
        constraint_statuses = self._analyze_constraints(solution, ir)
        executive_summary = self._build_executive_summary(
            status, objective_value, var_summaries, constraint_statuses
        )

        return AnalysisReport(
            status=status,
            objective_value=objective_value,
            variable_summaries=var_summaries,
            constraint_statuses=constraint_statuses,
            executive_summary=executive_summary,
            raw_solution=solution,
        )

    def _summarize_variables(
        self, variables: dict[str, Any], ir: IRModel | None
    ) -> list[VariableSummary]:
        """Create VariableSummary objects from raw variable values."""
        summaries: list[VariableSummary] = []
        for name, value in variables.items():
            is_indexed = isinstance(value, dict)
            description = ""
            if ir:
                for var in ir.variables:
                    if var.name == name:
                        description = var.description or ""
                        break
            summaries.append(
                VariableSummary(
                    name=name,
                    value=value,
                    description=description,
                    is_indexed=is_indexed,
                )
            )
        return summaries

    def _analyze_constraints(
        self, solution: dict[str, Any], ir: IRModel | None
    ) -> list[ConstraintStatus]:
        """Analyze constraint satisfaction from the solution.

        When the solver provides ``constraint_values`` we compute exact slack
        from the actual left-hand side values. Otherwise we fall back to a
        lightweight heuristic based on the constraint sense and right-hand side.
        """
        statuses: list[ConstraintStatus] = []
        if ir is None:
            return statuses

        constraint_values = solution.get("constraint_values", {})
        has_constraint_values = bool(constraint_values)

        for constr in ir.constraints:
            status = ConstraintStatus(name=constr.name)
            lhs_value = constraint_values.get(constr.name)
            rhs_value = self._parse_numeric_rhs(constr.rhs)
            status.lhs_value = float(lhs_value) if lhs_value is not None else None
            status.rhs_value = rhs_value

            if has_constraint_values and status.lhs_value is not None and rhs_value is not None:
                status.slack = self._compute_slack(constr.sense, status.lhs_value, rhs_value)
                status.is_binding = status.slack <= 1e-6
                status.is_violated = status.slack < -1e-6
            elif constr.sense == "eq" and rhs_value is not None and rhs_value != 0:
                # Fallback heuristic: equality with a non-zero RHS is likely binding
                status.is_binding = True
            statuses.append(status)
        return statuses

    def _parse_numeric_rhs(self, rhs: str | None) -> float | None:
        """Return RHS as a float when it is a plain numeric string, else None."""
        if rhs is None:
            return None
        try:
            return float(rhs)
        except ValueError:
            return None

    def _compute_slack(self, sense: str, lhs: float, rhs: float) -> float:
        """Compute constraint slack given the constraint sense."""
        if sense == "le":
            return rhs - lhs
        if sense == "ge":
            return lhs - rhs
        if sense == "eq":
            return abs(lhs - rhs)
        # Other senses (e.g. range) are not supported by this heuristic.
        return 0.0

    def _build_executive_summary(
        self,
        status: str,
        objective_value: float | None,
        var_summaries: list[VariableSummary],
        constraint_statuses: list[ConstraintStatus],
    ) -> str:
        """Generate a one-paragraph executive summary."""
        if status == "no_solution":
            return "求解器未找到可行解。请检查模型约束与数据。"
        if status == "mock":
            return "这是用于测试的 mock 解，结果没有实际意义。"

        lines = [f"求解状态：{status}。"]
        if objective_value is not None:
            lines.append(f"目标函数值：{objective_value:.4f}。")
        lines.append(f"活跃决策变量数：{len(var_summaries)}。")
        binding = sum(1 for c in constraint_statuses if c.is_binding)
        if binding > 0:
            lines.append(f"紧约束数量：{binding}。")
        return " ".join(lines)

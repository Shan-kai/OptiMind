"""Risk evaluator for optimization solutions."""

from __future__ import annotations

from typing import Any

from opti_mind.decision.models import RiskItem
from opti_mind.modeling.ir_models import IRModel


class RiskEvaluator:
    """Evaluate risks in the optimization solution."""

    def evaluate(self, solution: dict[str, Any], ir: IRModel | None = None) -> list[RiskItem]:
        """Identify risks from the solution and model structure."""
        risks: list[RiskItem] = []
        status = solution.get("status", "unknown")

        if status == "no_solution":
            risks.append(
                RiskItem(
                    category="feasibility",
                    severity="critical",
                    description="未找到可行解。问题可能过约束或数据不一致。",
                    mitigation="检查约束条件、放宽硬性限制或校验数据质量。",
                )
            )
            return risks

        if status == "mock":
            risks.append(
                RiskItem(
                    category="validity",
                    severity="high",
                    description="这是 mock 解，未基于真实优化计算。",
                    mitigation="生产决策请使用真实求解器（CPLEX）。",
                )
            )

        objective = solution.get("objective_value")
        if objective is not None and abs(objective) > 1e9:
            risks.append(
                RiskItem(
                    category="numerical",
                    severity="medium",
                    description=f"目标值（{objective}）过大，可能存在数值不稳定风险。",
                    mitigation="重新缩放参数或检查单位一致性。",
                )
            )

        if ir:
            for constr in ir.constraints:
                if constr.sense == "eq":
                    risks.append(
                        RiskItem(
                            category="binding_constraint",
                            severity="low",
                            description=f"等式约束 {constr.name} 为紧约束，无剩余松弛。",
                            mitigation="密切关注该约束；微小变化可能影响可行性。",
                        )
                    )

        return risks

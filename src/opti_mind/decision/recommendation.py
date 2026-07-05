"""Recommendation engine for business insights."""

from __future__ import annotations

from opti_mind.decision.models import AnalysisReport, Recommendation


class RecommendationEngine:
    """Generate business recommendations from an analysis report."""

    def generate(self, report: AnalysisReport) -> list[Recommendation]:
        """Produce actionable recommendations."""
        recommendations: list[Recommendation] = []

        if report.status == "no_solution":
            recommendations.append(
                Recommendation(
                    category="general",
                    priority="high",
                    title="检查模型可行性",
                    description="当前模型无可行解。请考虑放宽约束或检查输入数据。",
                    actionable=True,
                )
            )
            return recommendations

        # Recommend based on binding constraints
        binding = [c for c in report.constraint_statuses if c.is_binding]
        if binding:
            recommendations.append(
                Recommendation(
                    category="capacity",
                    priority="medium",
                    title="处理紧约束",
                    description=f"{len(binding)} 条约束为紧约束。可考虑扩容或调整需求。",
                    expected_impact="改善目标值并降低瓶颈风险。",
                    actionable=True,
                )
            )

        # Recommend based on objective sense
        if report.objective_value is not None:
            if report.objective_sense == "minimize":
                recommendations.append(
                    Recommendation(
                        category="cost",
                        priority="low",
                        title="成本优化",
                        description=(
                            f"当前最低成本为 {report.objective_value:.2f}。"
                            "可进一步寻找替代供应商或优化流程以降低成本。"
                        ),
                        actionable=True,
                    )
                )
            else:
                recommendations.append(
                    Recommendation(
                        category="revenue",
                        priority="low",
                        title="收益最大化",
                        description=(
                            f"当前最大收益为 {report.objective_value:.2f}。"
                            "可评估定价或需求策略以进一步提升收益。"
                        ),
                        actionable=True,
                    )
                )

        return recommendations

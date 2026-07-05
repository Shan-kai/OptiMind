"""独立单元测试：RecommendationEngine 的业务建议生成能力。"""

from __future__ import annotations

from opti_mind.decision.models import AnalysisReport, ConstraintStatus
from opti_mind.decision.recommendation import RecommendationEngine


class TestRecommendationEngine:
    """RecommendationEngine 的测试套件。"""

    def test_no_solution_recommendation(self) -> None:
        """无可行解报告应产生 high 优先级建议。"""
        engine = RecommendationEngine()
        report = AnalysisReport(status="no_solution")
        recs = engine.generate(report)

        assert len(recs) == 1
        assert recs[0].priority == "high"
        assert recs[0].category == "general"

    def test_binding_constraint_recommendation(self) -> None:
        """含 binding 约束的报告应产生容量相关建议。"""
        engine = RecommendationEngine()
        report = AnalysisReport(
            status="optimal",
            objective_value=100.0,
            objective_sense="minimize",
            constraint_statuses=[
                ConstraintStatus(name="capacity", is_binding=True),
            ],
        )
        recs = engine.generate(report)

        capacity_recs = [r for r in recs if r.category == "capacity"]
        assert len(capacity_recs) == 1
        assert capacity_recs[0].priority == "medium"

    def test_minimize_recommendation(self) -> None:
        """最小化目标应产生成本优化建议。"""
        engine = RecommendationEngine()
        report = AnalysisReport(
            status="optimal",
            objective_value=100.0,
            objective_sense="minimize",
        )
        recs = engine.generate(report)

        cost_recs = [r for r in recs if r.category == "cost"]
        assert len(cost_recs) == 1
        assert cost_recs[0].priority == "low"
        assert "成本优化" in cost_recs[0].title

    def test_maximize_recommendation(self) -> None:
        """最大化目标应产生收入最大化建议。"""
        engine = RecommendationEngine()
        report = AnalysisReport(
            status="optimal",
            objective_value=100.0,
            objective_sense="maximize",
        )
        recs = engine.generate(report)

        revenue_recs = [r for r in recs if r.category == "revenue"]
        assert len(revenue_recs) == 1
        assert revenue_recs[0].priority == "low"
        assert "收益最大化" in revenue_recs[0].title

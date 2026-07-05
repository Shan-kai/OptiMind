"""独立单元测试：RiskEvaluator 的风险评估能力。"""

from __future__ import annotations

import pytest

from opti_mind.decision.risk import RiskEvaluator
from opti_mind.modeling.ir_models import IRConstraint, IRModel


@pytest.fixture
def mock_solution() -> dict:
    """返回一个标准的 mock 最优解。"""
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
    """返回一个无可行解的 solver 输出。"""
    return {
        "status": "no_solution",
        "objective_value": None,
        "variables": {},
    }


class TestRiskEvaluator:
    """RiskEvaluator 的测试套件。"""

    def test_no_solution_risk(self, no_solution: dict) -> None:
        """无可行解时应产生 critical 级可行性风险。"""
        evaluator = RiskEvaluator()
        risks = evaluator.evaluate(no_solution)

        assert len(risks) == 1
        assert risks[0].severity == "critical"
        assert risks[0].category == "feasibility"

    def test_mock_risk(self) -> None:
        """mock 解时应产生 high 级有效性风险。"""
        evaluator = RiskEvaluator()
        mock_solution = {
            "status": "mock",
            "objective_value": 0.0,
            "variables": {},
        }
        risks = evaluator.evaluate(mock_solution)

        assert len(risks) == 1
        assert risks[0].severity == "high"
        assert risks[0].category == "validity"

    def test_large_objective_risk(self) -> None:
        """目标值极大时应产生 medium 级数值风险。"""
        evaluator = RiskEvaluator()
        solution = {
            "status": "optimal",
            "objective_value": 1e10,
            "variables": {},
        }
        risks = evaluator.evaluate(solution)

        assert len(risks) == 1
        assert risks[0].severity == "medium"
        assert risks[0].category == "numerical"

    def test_equality_constraint_risk(self, mock_solution: dict) -> None:
        """IR 含等式约束时应产生 low 级 binding 风险。"""
        evaluator = RiskEvaluator()
        ir = IRModel(
            problem_type="test",
            constraints=[
                IRConstraint(
                    name="balance",
                    expr="sum x_i",
                    sense="eq",
                    rhs="1",
                )
            ],
        )
        risks = evaluator.evaluate(mock_solution, ir)

        assert len(risks) == 1
        assert risks[0].severity == "low"
        assert risks[0].category == "binding_constraint"

    def test_optimal_no_risk(self, mock_solution: dict) -> None:
        """正常最优小目标值且无特殊结构时不应产生风险。"""
        evaluator = RiskEvaluator()
        risks = evaluator.evaluate(mock_solution)

        assert len(risks) == 0

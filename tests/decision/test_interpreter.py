"""独立单元测试：SolutionInterpreter 的决策解释能力。"""

from __future__ import annotations

import pytest

from opti_mind.decision.interpreter import SolutionInterpreter
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


@pytest.fixture
def mock_only_solution() -> dict:
    """返回一个标记为 mock 的 solution。"""
    return {
        "status": "mock",
        "objective_value": 0.0,
        "variables": {"x": 1.0},
    }


class TestSolutionInterpreter:
    """SolutionInterpreter 的测试套件。"""

    def test_interpret_optimal(self, mock_solution: dict) -> None:
        """验证 optimal 解能生成完整的 AnalysisReport。"""
        interpreter = SolutionInterpreter()
        report = interpreter.interpret(mock_solution)

        assert report.status == "optimal"
        assert report.objective_value == 42.0
        assert len(report.variable_summaries) == 2
        assert report.executive_summary

    def test_interpret_no_solution(self, no_solution: dict) -> None:
        """验证 no_solution 时执行摘要提示无可行解。"""
        interpreter = SolutionInterpreter()
        report = interpreter.interpret(no_solution)

        assert report.status == "no_solution"
        assert "未找到可行解" in report.executive_summary

    def test_interpret_mock(self, mock_only_solution: dict) -> None:
        """验证 mock 解的执行摘要提示测试用途。"""
        interpreter = SolutionInterpreter()
        report = interpreter.interpret(mock_only_solution)

        assert report.status == "mock"
        assert "mock" in report.executive_summary.lower()

    def test_analyze_constraints_with_values(self) -> None:
        """利用 solver 返回的 constraint_values 计算真实 slack。"""
        interpreter = SolutionInterpreter()
        ir = IRModel(
            problem_type="test",
            constraints=[
                IRConstraint(
                    name="capacity",
                    expr="sum x_i",
                    sense="le",
                    rhs="10",
                )
            ],
        )
        solution = {
            "status": "optimal",
            "constraint_values": {"capacity": 9.999999},
        }

        statuses = interpreter._analyze_constraints(solution, ir)

        assert len(statuses) == 1
        status = statuses[0]
        assert status.name == "capacity"
        assert status.lhs_value == pytest.approx(9.999999)
        assert status.slack == pytest.approx(1e-6)
        assert status.is_binding is True
        assert status.is_violated is False

    def test_analyze_constraints_fallback(self) -> None:
        """无 constraint_values 时，启发式逻辑仍能返回 ConstraintStatus。"""
        interpreter = SolutionInterpreter()
        ir = IRModel(
            problem_type="test",
            constraints=[
                IRConstraint(
                    name="demand",
                    expr="sum x_i",
                    sense="eq",
                    rhs="5",
                )
            ],
        )
        solution = {"status": "optimal"}

        statuses = interpreter._analyze_constraints(solution, ir)

        assert len(statuses) == 1
        assert statuses[0].name == "demand"
        assert statuses[0].is_binding is True

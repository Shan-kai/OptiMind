"""Tests for SensitivityAnalyzer."""

from __future__ import annotations

import pytest

from opti_mind.decision.models import SensitivityResult
from opti_mind.decision.sensitivity import SensitivityAnalyzer
from opti_mind.modeling.ir_models import IRConstraint, IRModel, IRParameter


@pytest.fixture
def facility_ir() -> IRModel:
    return IRModel(
        problem_type="facility_location",
        meta={
            "instance_parameters": {
                "Q": {"j1": 100.0, "j2": 200.0},
                "c": {("i1", "j1"): 5.0, ("i1", "j2"): 7.0},
                "d": {"i1": 50.0},
            }
        },
        parameters=[
            IRParameter(name="Q_j"),
            IRParameter(name="c_ij"),
            IRParameter(name="d_i"),
        ],
        constraints=[
            IRConstraint(
                name="capacity_j",
                expr="sum_{i in I} x_ij <= Q_j",
                sense="le",
            ),
            IRConstraint(
                name="demand_i",
                expr="sum_{j in J} x_ij >= d_i",
                sense="ge",
            ),
            IRConstraint(
                name="cost_link",
                expr="y_ij * c_ij <= budget",
                sense="le",
            ),
        ],
    )


@pytest.fixture
def mock_solution() -> dict:
    return {
        "status": "optimal",
        "objective_value": 42.0,
        "variables": {"x_ij": 1.0},
        "dual_values": {
            "capacity_j": 3.5,
            "demand_i": 0.0,
            "cost_link": -1.2,
        },
    }


@pytest.fixture
def analyzer() -> SensitivityAnalyzer:
    return SensitivityAnalyzer()


def test_analyze_fills_current_value_from_base_key(
    analyzer: SensitivityAnalyzer, facility_ir: IRModel, mock_solution: dict
) -> None:
    results = analyzer.analyze(mock_solution, facility_ir)
    by_name = {r.parameter_name: r for r in results}

    # Q_j maps to base key Q (indexed dict -> mean of 100 and 200)
    assert by_name["Q_j"].current_value == pytest.approx(150.0)
    # c_ij maps to base key c
    assert by_name["c_ij"].current_value == pytest.approx(6.0)
    # d_i maps to base key d
    assert by_name["d_i"].current_value == pytest.approx(50.0)


def test_analyze_fills_shadow_prices(
    analyzer: SensitivityAnalyzer, facility_ir: IRModel, mock_solution: dict
) -> None:
    results = analyzer.analyze(mock_solution, facility_ir)
    by_name = {r.parameter_name: r for r in results}

    assert by_name["Q_j"].shadow_price == pytest.approx(3.5)
    assert by_name["d_i"].shadow_price == pytest.approx(0.0)
    assert by_name["c_ij"].shadow_price == pytest.approx(-1.2)


def test_analyze_interpretation_for_positive_shadow_price(
    analyzer: SensitivityAnalyzer, facility_ir: IRModel, mock_solution: dict
) -> None:
    results = analyzer.analyze(mock_solution, facility_ir)
    q_result = next(r for r in results if r.parameter_name == "Q_j")
    assert q_result.shadow_price > 0
    assert "放松其右端项" in q_result.interpretation


def test_analyze_interpretation_for_zero_shadow_price(
    analyzer: SensitivityAnalyzer, facility_ir: IRModel, mock_solution: dict
) -> None:
    results = analyzer.analyze(mock_solution, facility_ir)
    d_result = next(r for r in results if r.parameter_name == "d_i")
    assert d_result.shadow_price == 0.0
    assert "非紧约束" in d_result.interpretation


def test_analyze_interpretation_for_negative_shadow_price(
    analyzer: SensitivityAnalyzer, facility_ir: IRModel, mock_solution: dict
) -> None:
    results = analyzer.analyze(mock_solution, facility_ir)
    c_result = next(r for r in results if r.parameter_name == "c_ij")
    assert c_result.shadow_price < 0
    assert "收紧其右端项" in c_result.interpretation


def test_analyze_uses_heuristic_when_no_dual_values(
    analyzer: SensitivityAnalyzer,
) -> None:
    ir = IRModel(
        problem_type="test",
        meta={"instance_parameters": {"capacity": {"j1": 100.0, "j2": 200.0}}},
        parameters=[IRParameter(name="capacity_j")],
        constraints=[
            IRConstraint(
                name="capacity_j",
                expr="sum_{i in I} x_ij <= capacity_j",
                sense="le",
            ),
        ],
    )
    solution_no_dual = {
        "status": "optimal",
        "objective_value": 42.0,
        "variables": {"x_ij": 1.0},
    }
    results = analyzer.analyze(solution_no_dual, ir)
    cap_result = results[0]

    assert cap_result.shadow_price is None
    assert cap_result.current_value == pytest.approx(150.0)
    assert cap_result.allowable_increase == pytest.approx(75.0)
    assert cap_result.allowable_decrease == pytest.approx(30.0)
    assert "容量参数" in cap_result.interpretation


def test_analyze_falls_back_to_full_param_name(
    analyzer: SensitivityAnalyzer,
) -> None:
    ir = IRModel(
        problem_type="test",
        meta={
            "instance_parameters": {
                "Q_j": 80.0,
            }
        },
        parameters=[IRParameter(name="Q_j")],
        constraints=[
            IRConstraint(
                name="capacity_j",
                expr="x <= Q_j",
                sense="le",
            ),
        ],
    )
    solution = {
        "status": "optimal",
        "objective_value": 1.0,
        "variables": {"x": 1.0},
        "dual_values": {"capacity_j": 2.0},
    }
    results = analyzer.analyze(solution, ir)
    assert len(results) == 1
    assert results[0].current_value == pytest.approx(80.0)
    assert results[0].shadow_price == pytest.approx(2.0)


def test_analyze_returns_empty_when_ir_is_none(
    analyzer: SensitivityAnalyzer, mock_solution: dict
) -> None:
    assert analyzer.analyze(mock_solution, None) == []


def test_analyze_scalar_parameter(
    analyzer: SensitivityAnalyzer,
) -> None:
    ir = IRModel(
        problem_type="test",
        meta={"instance_parameters": {"capacity": 1000.0}},
        parameters=[IRParameter(name="capacity")],
        constraints=[
            IRConstraint(
                name="capacity_limit",
                expr="cost <= capacity",
                sense="le",
            ),
        ],
    )
    solution = {
        "status": "optimal",
        "objective_value": 1.0,
        "variables": {"cost": 1.0},
        "dual_values": {"capacity_limit": 0.5},
    }
    results = analyzer.analyze(solution, ir)
    assert len(results) == 1
    assert results[0].current_value == pytest.approx(1000.0)
    assert results[0].shadow_price == pytest.approx(0.5)
    assert results[0].allowable_increase == pytest.approx(500.0)
    assert results[0].allowable_decrease == pytest.approx(200.0)


def test_analyze_result_is_pydantic_model(
    analyzer: SensitivityAnalyzer, facility_ir: IRModel, mock_solution: dict
) -> None:
    results = analyzer.analyze(mock_solution, facility_ir)
    assert all(isinstance(r, SensitivityResult) for r in results)

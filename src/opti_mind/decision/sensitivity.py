"""Sensitivity analysis for optimization solutions."""

from __future__ import annotations

from typing import Any

from opti_mind.decision.models import SensitivityResult
from opti_mind.modeling.ir_models import IRConstraint, IRModel, IRParameter


def _extract_base_key(param_name: str) -> str:
    """Return the base parameter key without index subscripts.

    For example ``Q_j`` -> ``Q``, ``c_ij`` -> ``c``.
    """
    return param_name.split("_")[0]


def _resolve_current_value(
    instance_parameters: dict[str, Any], param_name: str, base_key: str
) -> float:
    """Resolve the current numeric value of a parameter from instance data.

    The value is looked up first by the parameter base key, then by the full
    parameter name. Indexed parameters (``dict``) are summarized by the mean of
    their values. If no value is found, ``0.0`` is returned.
    """
    raw_value = instance_parameters.get(base_key)
    if raw_value is None:
        raw_value = instance_parameters.get(param_name)
    if raw_value is None:
        return 0.0
    if isinstance(raw_value, dict):
        values = [float(v) for v in raw_value.values() if isinstance(v, (int, float))]
        return sum(values) / len(values) if values else 0.0
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return 0.0


def _parameter_used_in_constraint(base_key: str, constraint: IRConstraint) -> bool:
    """Check whether a parameter base key participates in a constraint.

    Matching is token-based so that ``c`` does not match inside ``cost`` or
    ``abc``. A token equals ``base_key`` or starts with ``base_key + "_"``.
    """
    targets = [constraint.expr]
    if constraint.rhs is not None:
        targets.append(constraint.rhs)
    for text in targets:
        if not text:
            continue
        for token in _tokenize_expression(text):
            if token == base_key or token.startswith(base_key + "_"):
                return True
    return False


def _tokenize_expression(expr: str) -> list[str]:
    """Split a symbolic expression into alphanumeric/underscore tokens."""
    tokens: list[str] = []
    current = ""
    for char in expr:
        if char.isalnum() or char == "_":
            current += char
        else:
            if current:
                tokens.append(current)
                current = ""
    if current:
        tokens.append(current)
    return tokens


def _find_shadow_price(
    param: IRParameter, constraints: list[IRConstraint], dual_values: dict[str, float]
) -> float | None:
    """Return the dual value for the first constraint that uses this parameter.

    Parameters are mapped to constraints by searching each constraint's
    expression and right-hand side for the parameter's base key. If no matching
    constraint has a dual value, ``None`` is returned.
    """
    base_key = _extract_base_key(param.name)
    for constraint in constraints:
        if not _parameter_used_in_constraint(base_key, constraint):
            continue
        shadow_price = dual_values.get(constraint.name)
        if shadow_price is not None:
            return float(shadow_price)
    return None


def _compute_bounds(
    param: IRParameter, current_value: float, shadow_price: float | None
) -> tuple[float | None, float | None, str]:
    """Compute allowable bounds and a heuristic interpretation for a parameter.

    Returns a tuple of ``(allowable_increase, allowable_decrease, interpretation)``.
    When ``shadow_price`` is provided, the interpretation reflects dual
    information; otherwise a heuristic description is used.
    """
    increase: float | None
    decrease: float | None
    name = param.name.lower()
    if "capacity" in name or "cap" in name:
        if current_value > 0:
            increase = current_value * 0.5
            decrease = current_value * 0.2
        else:
            increase = None
            decrease = None
        interpretation = "容量参数；增加容量可能改善目标值。"
    elif "cost" in name or "price" in name:
        if current_value > 0:
            increase = current_value * 0.3
            decrease = current_value * 0.3
        else:
            increase = None
            decrease = None
        interpretation = "成本参数；变化会直接影响目标值。"
    elif "demand" in name or "d" in name:
        if current_value > 0:
            increase = current_value * 0.25
            decrease = current_value * 0.15
        else:
            increase = None
            decrease = None
        interpretation = "需求参数；影响可行域。"
    else:
        increase = None
        decrease = None
        interpretation = "无法对该参数的敏感性进行分类。"

    if shadow_price is not None:
        if shadow_price > 0:
            interpretation = "对应约束为紧约束；放松其右端项可改善目标值。"
        elif shadow_price < 0:
            interpretation = "对应约束为紧约束；收紧其右端项可改善目标值。"
        else:
            interpretation = "对应约束为非紧约束；该资源仍有松弛。"

    return increase, decrease, interpretation


class SensitivityAnalyzer:
    """Analyze sensitivity of the solution to parameter changes."""

    def analyze(
        self, solution: dict[str, Any], ir: IRModel | None = None
    ) -> list[SensitivityResult]:
        """Return sensitivity results for key parameters.

        When the solver provides dual values, real shadow prices are reported.
        Otherwise, heuristic bounds are provided.
        """
        results: list[SensitivityResult] = []
        if ir is None:
            return results

        instance_parameters = ir.meta.get("instance_parameters", {})
        dual_values = solution.get("dual_values") or {}

        for param in ir.parameters:
            base_key = _extract_base_key(param.name)
            current_value = _resolve_current_value(instance_parameters, param.name, base_key)
            shadow_price = _find_shadow_price(param, ir.constraints, dual_values)
            increase, decrease, interpretation = _compute_bounds(param, current_value, shadow_price)

            result = SensitivityResult(
                parameter_name=param.name,
                current_value=current_value,
                allowable_increase=increase,
                allowable_decrease=decrease,
                shadow_price=shadow_price,
                interpretation=interpretation,
            )
            results.append(result)
        return results

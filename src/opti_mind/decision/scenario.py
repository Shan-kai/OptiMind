"""Scenario engine for what-if analysis."""

from __future__ import annotations

import copy
import logging
import re
from collections.abc import Callable
from typing import Any

from opti_mind.decision.models import ScenarioComparison
from opti_mind.modeling.ir_models import IRModel
from opti_mind.solver.router import SolverRouter

logger = logging.getLogger(__name__)

# Matches "<param_key>[<index_path>] <op>= <value>" where param_key is a base
# or aliased parameter symbol (e.g. Q, c_ij, d_i, C). The optional index_path
# supports both comma-separated (c_ij[a1,t1]) and nested-bracket
# (c_ij[a1][t1]) forms for modifying a single matrix/tensor element.
_CHANGE_PATTERN = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)"
    r"(.*?)"
    r"\s*(\*=|\+=|-=|/=)\s*"
    r"([-+]?\s*(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*$"
)

_Operators = dict[str, Callable[[float, float], float]]


def _get_operators() -> _Operators:
    """Return the supported compound-assignment operators."""
    return {
        "*=": lambda a, b: a * b,
        "+=": lambda a, b: a + b,
        "-=": lambda a, b: a - b,
        "/=": lambda a, b: a / b,
    }


class ScenarioEngine:
    """Run what-if scenarios by modifying model parameters and re-solving."""

    def __init__(self, solver_router: SolverRouter | None = None) -> None:
        """Initialize the engine with an optional SolverRouter.

        Args:
            solver_router: Router used to re-solve modified IRs. When omitted,
                a default ``SolverRouter()`` is constructed.
        """
        self._solver_router = solver_router or SolverRouter()

    def compare(
        self,
        baseline_solution: dict[str, Any],
        ir: IRModel | None,
        scenarios: list[dict[str, Any]] | None = None,
    ) -> list[ScenarioComparison]:
        """Compare baseline against user-defined scenarios.

        Each scenario is a dict with at least a ``changes`` list of parameter
        modification strings. The engine re-solves the modified IR to obtain a
        real objective-value delta.
        """
        comparisons: list[ScenarioComparison] = []
        if baseline_solution is None:
            logger.warning("Baseline solution is None, returning empty scenario comparison list")
            return comparisons

        baseline_obj = baseline_solution.get("objective_value")

        if scenarios is None:
            # Generate default scenarios
            scenarios = self._default_scenarios(ir)

        for scenario in scenarios:
            name = scenario.get("name", "unnamed")
            delta = self._estimate_delta(baseline_solution, ir, scenario)
            scenario_obj = baseline_obj + delta if baseline_obj is not None else None
            delta_pct = (delta / baseline_obj * 100) if baseline_obj and baseline_obj != 0 else None

            comparisons.append(
                ScenarioComparison(
                    scenario_name=name,
                    baseline_objective=baseline_obj,
                    scenario_objective=scenario_obj,
                    objective_delta=delta,
                    objective_delta_pct=delta_pct,
                    key_changes=scenario.get("changes", []),
                    recommendation=scenario.get("recommendation", ""),
                )
            )
        return comparisons

    def _default_scenarios(self, ir: IRModel | None) -> list[dict[str, Any]]:
        """Generate default what-if scenarios based on parameter types."""
        scenarios: list[dict[str, Any]] = []
        if ir is None:
            return scenarios

        for param in ir.parameters:
            if "capacity" in param.name.lower():
                scenarios.append(
                    {
                        "name": f"{param.name} 增加 20%",
                        "changes": [f"{param.name} *= 1.2"],
                        "recommendation": "评估扩容可行性。",
                    }
                )
            elif "cost" in param.name.lower():
                scenarios.append(
                    {
                        "name": f"{param.name} 降低 10%",
                        "changes": [f"{param.name} *= 0.9"],
                        "recommendation": "争取更优费率或寻找替代方案。",
                    }
                )
        return scenarios

    def _apply_scenario(self, ir: IRModel | None, scenario: dict[str, Any]) -> IRModel | None:
        """Create a deep-copied IR with scenario parameter changes applied.

        Supported change formats:
            - ``"Q *= 1.2"``
            - ``"c_ij *= 0.9"``
            - ``"d_i += 10"``
            - ``"C -= 5"``
            - ``"c_ij[a1,t1] -= 10"`` (single matrix element)
            - ``"c_ij[a1][t1] -= 10"`` (nested-bracket form)

        The modification is applied recursively to scalar leaves unless an
        index path is given, in which case only the targeted element is
        updated. If the changed
        key shares a base symbol with aliased keys in ``instance_parameters``
        (e.g. ``c`` and ``c_ij``), all matching keys are updated so the solver
        compiler sees a consistent value.

        Unparseable or unknown changes are logged as warnings and skipped.

        Args:
            ir: The original IR model.
            scenario: Scenario dict containing a ``changes`` list.

        Returns:
            A new IRModel with modified parameters, or ``None`` when ``ir`` is
            ``None``.
        """
        if ir is None:
            logger.warning("Cannot apply scenario without an IR model")
            return None

        instance_parameters = copy.deepcopy(ir.meta.get("instance_parameters", {}))
        operators = _get_operators()

        for change in scenario.get("changes", []):
            if not isinstance(change, str):
                logger.warning("Skipping non-string scenario change: %s", change)
                continue

            match = _CHANGE_PATTERN.match(change)
            if not match:
                logger.warning("Could not parse scenario change '%s', skipping", change)
                continue

            key, index_part, op_symbol, value_str = match.groups()
            operator = operators.get(op_symbol)
            if operator is None:
                logger.warning(
                    "Unsupported operator '%s' in change '%s', skipping", op_symbol, change
                )
                continue

            try:
                value = float(value_str)
            except ValueError:
                logger.warning("Invalid numeric value in change '%s', skipping", change)
                continue

            base = key.split("_", 1)[0]
            index_path = self._parse_index_path(index_part)
            matched_any = False
            for param_key in list(instance_parameters.keys()):
                if param_key.split("_", 1)[0] == base:
                    instance_parameters[param_key] = self._apply_value(
                        instance_parameters[param_key],
                        operator,
                        value,
                        index_path=index_path,
                    )
                    matched_any = True

            if not matched_any:
                logger.warning("Scenario key '%s' not found in instance parameters, skipping", key)

        ir_modified = ir.model_copy(deep=True)
        ir_modified.meta = {**ir_modified.meta, "instance_parameters": instance_parameters}
        return ir_modified

    @staticmethod
    def _parse_index_path(raw: str | None) -> list[str]:
        """Parse an index path string into a list of keys.

        Supports both comma-separated inside a single bracket (``[a1,t1]``)
        and nested-bracket forms (``[a1][t1]``).
        """
        if not raw:
            return []
        parts: list[str] = []
        # Extract each bracketed segment, e.g. "[a1][t1]" -> ["a1", "t1"].
        for segment in re.findall(r"\[([^\]]+)\]", raw):
            # Each segment may itself be comma-separated.
            for part in segment.split(","):
                stripped = part.strip()
                if stripped:
                    parts.append(stripped)
        return parts

    @staticmethod
    def _apply_value(
        current: Any,
        operator: Callable[[float, float], float],
        value: float,
        index_path: list[str] | None = None,
    ) -> Any:
        """Apply ``operator`` to ``current``.

        When ``index_path`` is empty, dicts are traversed recursively and all
        scalar leaves are updated. When ``index_path`` is provided, only the
        value at that path is modified; intermediate missing dicts are created
        as needed. Non-numeric leaves are left unchanged.
        """
        path = index_path or []
        if not path:
            if isinstance(current, dict):
                return {
                    k: ScenarioEngine._apply_value(v, operator, value, index_path=None)
                    for k, v in current.items()
                }
            try:
                return operator(float(current), value)
            except (TypeError, ValueError):
                return current

        head, *tail = path
        if not isinstance(current, dict):
            # Cannot traverse into a non-dict; leave unchanged.
            return current

        result = dict(current)
        if head not in result:
            # If the path does not exist yet and we still need to go deeper,
            # create an empty dict to allow the modification.
            if tail:
                result[head] = {}
            else:
                return result
        result[head] = ScenarioEngine._apply_value(result[head], operator, value, index_path=tail)
        return result

    def _estimate_delta(
        self,
        baseline: dict[str, Any],
        ir: IRModel | None,
        scenario: dict[str, Any],
    ) -> float:
        """Compute the objective-value delta by re-solving the modified IR.

        Args:
            baseline: The baseline solution dict.
            ir: The original IR model.
            scenario: Scenario dict describing the parameter changes.

        Returns:
            ``scenario_objective - baseline_objective``. If either objective is
            unavailable or the scenario solve fails, returns ``0.0`` and logs a
            warning.
        """
        baseline_obj = baseline.get("objective_value") if baseline else None
        if baseline_obj is None:
            logger.warning("Baseline objective value unavailable, returning 0.0 delta")
            return 0.0

        ir_modified = self._apply_scenario(ir, scenario)
        if ir_modified is None:
            return 0.0

        try:
            scenario_solution = self._solver_router.solve(ir_modified)
        except Exception as exc:  # noqa: BLE001 - scenario must not crash report
            logger.warning("Scenario re-solve failed: %s", exc)
            return 0.0

        scenario_obj = (
            scenario_solution.get("objective_value")
            if isinstance(scenario_solution, dict)
            else None
        )
        if scenario_obj is None:
            logger.warning("Scenario solution did not return an objective value")
            return 0.0

        return float(scenario_obj) - float(baseline_obj)

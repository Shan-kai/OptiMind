"""CPLEX backend: compiles IR to docplex and solves with CPLEX."""

from __future__ import annotations

from typing import Any

from opti_mind.config import configure_cplex_env, get_settings
from opti_mind.modeling.ir_models import IRModel
from opti_mind.solver.backends.base import SolverBackend
from opti_mind.solver.compiler import IRToModelCompiler


def _key_str(key: Any) -> str:
    """Convert an index key into the string suffix used in expanded names."""
    return "_".join(str(k) for k in key) if isinstance(key, tuple) else str(key)


def _expected_constraint_ids(
    constraint: Any,
    var_defs: dict[str, Any],
    set_members: dict[str, list[Any]],
    params: dict[str, Any],
    arc_lookup: dict[str, dict[str, Any]],
) -> list[str]:
    """Return the expected constraint identifiers for an IR constraint.

    Mirrors the expansion order in ``IRToModelCompiler._compile_constraint_rows``
    so docplex constraints can be aligned with IR constraint names after solving.
    """
    ids: list[str] = []
    for row_key, _entries, _rhs in IRToModelCompiler._compile_constraint_rows(
        constraint, var_defs, set_members, params, arc_lookup
    ):
        if row_key is None:
            ids.append(constraint.name)
        else:
            ids.append(f"{constraint.name}_{_key_str(row_key)}")
    return ids


class CplexBackend(SolverBackend):
    """Solve an IR using docplex + the local CPLEX runtime."""

    name = "cplex"

    def __init__(self) -> None:
        configure_cplex_env()

    @classmethod
    def available(cls) -> bool:
        """Check that docplex and cplex are importable and a model can be created."""
        try:
            import cplex  # noqa: F401
            import docplex  # noqa: F401
            from docplex.mp.model import Model

            Model("availability_check")
            return True
        except Exception:
            return False

    def solve(self, ir: IRModel) -> dict[str, Any]:
        """Compile IR to docplex Model, solve, extract solution.

        Extracts primal variable values together with dual values, reduced costs
        and constraint LHS values when CPLEX provides them.
        """
        compiler = IRToModelCompiler()
        model, var_index = compiler.compile(ir)
        set_members = IRToModelCompiler._build_set_members(ir)
        arc_lookup = IRToModelCompiler._build_arc_lookup(ir.sets, set_members)
        params = IRToModelCompiler._build_params(ir)
        var_defs = {v.name: v for v in ir.variables}
        settings = get_settings()
        model.set_time_limit(int(settings.solver_timeout))

        solution = model.solve()

        if solution is None:
            return {
                "status": "no_solution",
                "objective_value": None,
                "variables": {},
                "dual_values": None,
                "reduced_costs": None,
                "constraint_values": None,
            }

        var_values: dict[str, Any] = {}
        reduced_costs: dict[str, Any] = {}
        for name, obj in var_index.items():
            if isinstance(obj, dict):
                var_values[name] = {}
                reduced_costs[name] = {}
                for key, var in obj.items():
                    key_str = _key_str(key)
                    var_values[name][key_str] = (
                        var.solution_value if hasattr(var, "solution_value") else None
                    )
                    # Reduced costs are only defined for LP/continuous problems;
                    # docplex raises for integer/MIP variables.
                    try:
                        reduced_costs[name][key_str] = var.reduced_cost
                    except Exception:  # noqa: BLE001
                        reduced_costs[name][key_str] = None
            else:
                var_values[name] = obj.solution_value if hasattr(obj, "solution_value") else None
                try:
                    reduced_costs[name] = obj.reduced_cost
                except Exception:  # noqa: BLE001
                    reduced_costs[name] = None

        # Align docplex constraints with IR constraint names in expansion order.
        docplex_constraints = list(model.iter_constraints())
        constraint_map: dict[str, Any] = {}
        cursor = 0
        for constraint in ir.constraints:
            expected_ids = _expected_constraint_ids(
                constraint, var_defs, set_members, params, arc_lookup
            )
            count = len(expected_ids)
            available = len(docplex_constraints) - cursor
            if count == 0 or available <= 0:
                continue
            if count > available:
                count = available
                expected_ids = [f"{constraint.name}_{i}" for i in range(count)]
            for ct_id in expected_ids:
                constraint_map[ct_id] = docplex_constraints[cursor]
                cursor += 1

        dual_values: dict[str, float] = {}
        constraint_values: dict[str, float] = {}
        for ct_id, ct in constraint_map.items():
            try:
                dual = getattr(ct, "dual_value", None)
                if dual is not None:
                    dual_values[ct_id] = float(dual)
            except Exception:  # noqa: BLE001
                pass
            try:
                lhs_value = solution.get_value(ct.lhs) if hasattr(solution, "get_value") else None
                if lhs_value is not None:
                    constraint_values[ct_id] = float(lhs_value)
            except Exception:  # noqa: BLE001
                pass

        return {
            "status": "optimal",
            "objective_value": model.objective_value,
            "variables": var_values,
            "dual_values": dual_values,
            "reduced_costs": reduced_costs,
            "constraint_values": constraint_values,
        }

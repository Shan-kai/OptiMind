"""Mock backend: returns a trivial all-zero solution without solving."""

from __future__ import annotations

from typing import Any

from opti_mind.modeling.ir_models import IRModel
from opti_mind.solver.backends.base import SolverBackend
from opti_mind.solver.compiler import IRToModelCompiler


class MockBackend(SolverBackend):
    """Returns a feasible all-zero solution for testing without CPLEX."""

    name = "mock"

    @classmethod
    def available(cls) -> bool:
        """Mock backend is always available."""
        return True

    def solve(self, ir: IRModel) -> dict[str, Any]:
        """Return a trivial solution: all variables set to 0.

        Also returns zero-filled dual values, reduced costs and constraint LHS
        values so the result dict has the same shape as real solver backends.
        """
        var_values: dict[str, Any] = {}
        reduced_costs: dict[str, Any] = {}
        for var in ir.variables:
            if var.sets:
                # Indexed variable — produce indices from sets
                set_members: dict[str, list[Any]] = {}
                for s in ir.sets:
                    if isinstance(s.members, list):
                        set_members[s.name] = s.members
                    elif s.members == "from_instance":
                        set_members[s.name] = list(range(3))
                    else:
                        set_members[s.name] = list(range(3))
                indices = IRToModelCompiler._cartesian(
                    [set_members.get(s, [0, 1, 2]) for s in var.sets]
                )
                var_values[var.name] = {"_".join(str(i) for i in idx): 0.0 for idx in indices}
                reduced_costs[var.name] = {"_".join(str(i) for i in idx): 0.0 for idx in indices}
            else:
                var_values[var.name] = 0.0
                reduced_costs[var.name] = 0.0

        dual_values = {constraint.name: 0.0 for constraint in ir.constraints}
        constraint_values = {constraint.name: 0.0 for constraint in ir.constraints}

        return {
            "status": "mock",
            "objective_value": 0.0,
            "variables": var_values,
            "dual_values": dual_values,
            "reduced_costs": reduced_costs,
            "constraint_values": constraint_values,
        }

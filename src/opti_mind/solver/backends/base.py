"""Solver backend abstraction layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from opti_mind.modeling.ir_models import IRModel


class SolverBackend(ABC):
    """Abstract base class for a solver backend.

    Each concrete backend must define a unique ``name`` and implement
    ``solve()``.  The optional ``available()`` class method allows the
    registry to skip backends whose runtime dependencies are missing.
    """

    name: str = ""

    @classmethod
    @abstractmethod
    def available(cls) -> bool:
        """Return True if this backend can be used in the current environment."""
        ...

    @abstractmethod
    def solve(self, ir: IRModel) -> dict[str, Any]:
        """Solve the IR and return a result dict.

        The result format is kept stable for consumers:

            {
                "status": str,            # e.g. "optimal", "feasible", "no_solution", "mock"
                "objective_value": float | None,
                "variables": dict[str, Any],
                "dual_values": dict[str, float] | None,      # constraint id -> shadow price
                "reduced_costs": dict[str, Any] | None,      # variable name -> reduced cost
                "constraint_values": dict[str, float] | None,  # constraint id -> LHS value
            }

        The three dual-related fields are optional. Backends should return
        ``None`` for all of them when the problem has no feasible solution or
        when the solver cannot provide dual information.
        """
        ...

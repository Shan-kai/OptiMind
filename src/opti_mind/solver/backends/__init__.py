"""Solver backend package."""

from opti_mind.solver.backends.base import SolverBackend
from opti_mind.solver.backends.cplex_backend import CplexBackend
from opti_mind.solver.backends.highs_backend import HighsBackend
from opti_mind.solver.backends.mock_backend import MockBackend
from opti_mind.solver.backends.registry import DEFAULT_REGISTRY, SolverBackendRegistry

DEFAULT_REGISTRY.register(CplexBackend)
DEFAULT_REGISTRY.register(MockBackend)
DEFAULT_REGISTRY.register(HighsBackend)

__all__ = [
    "SolverBackend",
    "CplexBackend",
    "HighsBackend",
    "MockBackend",
    "SolverBackendRegistry",
    "DEFAULT_REGISTRY",
]

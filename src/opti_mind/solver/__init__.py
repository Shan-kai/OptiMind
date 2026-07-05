"""Solver Layer: compiles IR to a solver model and executes optimization."""

from opti_mind.solver.backends import (
    DEFAULT_REGISTRY,
    CplexBackend,
    HighsBackend,
    MockBackend,
    SolverBackend,
    SolverBackendRegistry,
)
from opti_mind.solver.compiler import IRToModelCompiler
from opti_mind.solver.router import SolverRouter

__all__ = [
    "CplexBackend",
    "HighsBackend",
    "DEFAULT_REGISTRY",
    "IRToModelCompiler",
    "MockBackend",
    "SolverBackend",
    "SolverBackendRegistry",
    "SolverRouter",
]

"""SolverRouter: selects the right solver backend based on configuration."""

from __future__ import annotations

from typing import Any

from opti_mind.config import get_settings
from opti_mind.core.exceptions import SolverError
from opti_mind.modeling.ir_models import IRModel
from opti_mind.solver.backends import DEFAULT_REGISTRY, SolverBackend, SolverBackendRegistry

_SOLVER_UNAVAILABLE_ERROR = (
    "当前环境未检测到 CPLEX 许可证/运行库，请切换到 mock 或 highs 后端："
    "OPTI_MIND_SOLVER_BACKEND=mock"
)


def _solver_unavailable_response() -> dict[str, Any]:
    """Return a structured result when the configured solver is unavailable.

    Keeps the standard solution shape so downstream consumers can safely
    read ``status``, ``objective_value`` and ``variables``.
    """
    return {
        "status": "solver_unavailable",
        "objective_value": None,
        "variables": {},
        "error": _SOLVER_UNAVAILABLE_ERROR,
    }


def _is_solver_unavailable_error(exc: BaseException) -> bool:
    """Return True when ``exc`` indicates the configured solver cannot be used.

    Heuristics cover:
    - explicit ``SolverError`` reporting the backend is not available;
    - ``ImportError`` (missing solver Python package);
    - ``RuntimeError`` mentioning license / CPLEX / docplex / availability;
    - exception types belonging to the ``cplex`` or ``docplex`` packages.
    """
    message = str(exc).lower()
    if isinstance(exc, SolverError) and "not available" in message:
        return True
    if isinstance(exc, ImportError):
        return True
    unavailable_keywords = ("cplex", "docplex", "license", "not available")
    if isinstance(exc, RuntimeError) and any(kw in message for kw in unavailable_keywords):
        return True
    module = getattr(type(exc), "__module__", "") or ""
    if module.startswith("cplex"):
        return True
    # docplex.mp.utils.DOcplexException is used for modeling errors (e.g.
    # "reduced costs are not available for integer problems") and must not be
    # misreported as a license/runtime unavailability.
    return module.startswith("cplex") or (
        module.startswith("docplex") and not module.startswith("docplex.mp.utils")
    )


class SolverRouter:
    """Routes solving to the configured backend via the backend registry.

    Reads ``solver_backend`` from settings.  Backends are discovered through
    ``SolverBackendRegistry`` instead of hard-coded conditionals.
    """

    def __init__(self, registry: SolverBackendRegistry | None = None) -> None:
        self._settings = get_settings()
        self._registry = registry or DEFAULT_REGISTRY

    def _get_backend(self) -> SolverBackend:
        backend_cls = self._registry.get(self._settings.solver_backend)
        if not backend_cls.available():
            raise SolverError(
                f"Solver backend '{backend_cls.name}' is not available in this environment"
            )
        return backend_cls()

    def solve(self, ir: IRModel) -> dict[str, Any]:
        """Solve the IR using the configured backend.

        When the backend reports itself (or fails at runtime) as unavailable,
        returns a structured ``solver_unavailable`` dict instead of raising.
        Other solver failures are still wrapped as ``SolverError``.
        """
        try:
            backend = self._get_backend()
            return backend.solve(ir)
        except ValueError:
            # Unknown backend name is a configuration error, not a solver failure.
            raise
        except SolverError as exc:
            if _is_solver_unavailable_error(exc):
                return _solver_unavailable_response()
            raise
        except Exception as exc:
            if _is_solver_unavailable_error(exc):
                return _solver_unavailable_response()
            raise SolverError(f"Solver failed: {exc}") from exc

    def solve_dict(self, ir_data: dict[str, Any]) -> dict[str, Any]:
        """Solve from an IR dict (e.g. from workflow state).

        Mirrors ``solve()``: solver-unavailability is returned as a structured
        dict, while IR validation or unknown backend errors are re-raised.
        """
        try:
            ir = IRModel.model_validate(ir_data)
            return self.solve(ir)
        except ValueError:
            # IR validation / unknown backend is not a solver failure.
            raise
        except SolverError as exc:
            if _is_solver_unavailable_error(exc):
                return _solver_unavailable_response()
            raise
        except Exception as exc:
            if _is_solver_unavailable_error(exc):
                return _solver_unavailable_response()
            raise SolverError(f"Solver failed: {exc}") from exc

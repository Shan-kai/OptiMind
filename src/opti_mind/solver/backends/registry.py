"""Backend registry supporting runtime discovery of solver backends."""

from __future__ import annotations

from opti_mind.solver.backends.base import SolverBackend


class SolverBackendRegistry:
    """Registers solver backends and provides lookup/discovery."""

    def __init__(self) -> None:
        self._backends: dict[str, type[SolverBackend]] = {}

    def register(self, backend_cls: type[SolverBackend]) -> None:
        """Register a backend class under its lower-cased name."""
        name = backend_cls.name.lower()
        if not name:
            raise ValueError(f"{backend_cls.__name__} must define a non-empty name")
        self._backends[name] = backend_cls

    def get(self, name: str) -> type[SolverBackend]:
        """Return the backend class registered under ``name``.

        Raises:
            ValueError: if no backend is registered for the given name.
        """
        key = name.lower()
        backend_cls = self._backends.get(key)
        if backend_cls is None:
            raise ValueError(f"Unknown solver backend: {name}")
        return backend_cls

    def list_available(self) -> list[str]:
        """Return names of all backends reporting themselves as available."""
        return sorted(cls.name for cls in self._backends.values() if cls.available())

    def list_registered(self) -> list[str]:
        """Return names of all registered backends (regardless of availability)."""
        return sorted(self._backends.keys())


DEFAULT_REGISTRY = SolverBackendRegistry()

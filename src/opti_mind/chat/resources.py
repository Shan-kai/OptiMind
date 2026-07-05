"""Lightweight resource loader for skills, prompts, and project rules.

Resources are plain text or Jinja2 templates stored under:

- The project root (e.g. ``CLAUDE.md``, ``AGENTS.md``)
- ``skills/`` relative to the project root
- ``prompts/`` relative to the project root

This keeps LLM prompts out of source code and makes them hot-swappable without
redeploying the backend.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, Template, TemplateNotFound


class _ProjectRootLoader(BaseLoader):
    """Jinja2 loader that resolves templates under the project root."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def get_source(
        self,
        environment: Environment,
        template: str,
    ) -> tuple[str, str, Callable[[], bool]]:
        path = self.root / template
        if not path.exists():
            raise TemplateNotFound(template)
        source = path.read_text(encoding="utf-8")
        mtime = path.stat().st_mtime

        def uptodate() -> bool:
            try:
                return path.stat().st_mtime == mtime
            except OSError:
                return False

        return source, str(path), uptodate


_ENV_ROOT: Path | None = None


def _project_root() -> Path:
    """Return the project root by walking up from this file."""
    marker = Path(__file__).resolve()
    for parent in marker.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent
    return marker.parent


def _env_root() -> Path | None:
    env = os.environ.get("OPTI_MIND_RESOURCE_ROOT")
    return Path(env) if env else None


def _load_jinja_env() -> Environment:
    root = _ENV_ROOT or _env_root() or _project_root()
    return Environment(loader=_ProjectRootLoader(root), autoescape=False)


_JINJA_ENV = _load_jinja_env()


def load_resource(name: str) -> str | None:
    """Load a project resource file as text.

    ``name`` is a relative path such as ``"skills/field_mapping_agent.md"`` or
    ``"CLAUDE.md"``. Returns ``None`` if the file does not exist.
    """
    try:
        template: Template = _JINJA_ENV.get_template(name)
        return template.render()
    except TemplateNotFound:
        return None


def render_template(template_text: str, variables: dict[str, Any]) -> str:
    """Render a Jinja2 template string with the given variables."""
    return Environment(autoescape=False).from_string(template_text).render(variables)


def get_project_root() -> Path:
    """Expose the detected project root for callers that need absolute paths."""
    return _project_root()


def set_resource_root(root: Path) -> None:
    """Switch the resource loader root at runtime (useful for tests)."""
    global _ENV_ROOT, _JINJA_ENV  # noqa: PLW0603
    _ENV_ROOT = root
    _JINJA_ENV = Environment(loader=_ProjectRootLoader(root), autoescape=False)

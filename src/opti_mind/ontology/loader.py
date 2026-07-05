"""YAML loader for optimization ontology entries.

Reads ontology templates from YAML files and converts them into
``OntologyEntry`` instances. Handles string-to-enum conversion for
problem types, variable kinds, constraint senses, and objective senses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from opti_mind.ontology.models import OntologyEntry, ProblemType


def load_ontology_entry(path: str | Path) -> OntologyEntry:
    """Load a single ontology entry from a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        The parsed ``OntologyEntry``.

    Raises:
        ValueError: If the file is missing, empty, not valid YAML, or
            does not represent a valid ``OntologyEntry``.
    """
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Ontology file not found: {path}")

    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in ontology file '{path}': {exc}") from exc

    if raw is None:
        raise ValueError(f"Ontology YAML file is empty: {path}")
    if not isinstance(raw, dict):
        raise ValueError(f"Ontology YAML must contain a mapping at the top level: {path}")

    try:
        return OntologyEntry(**raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid ontology content in '{path}': {exc}") from exc


def load_ontology_directory(
    directory: str | Path,
) -> dict[ProblemType, OntologyEntry]:
    """Load all ontology entries from a directory of YAML files.

    Files matching ``*.yaml`` or ``*.yml`` are loaded in sorted order.

    Args:
        directory: Directory containing ontology YAML files.

    Returns:
        Mapping from ``ProblemType`` to ``OntologyEntry``.

    Raises:
        ValueError: If the directory does not exist, a file cannot be
            parsed, or the same ``ProblemType`` appears in multiple files.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"Ontology directory not found: {directory}")

    entries: dict[ProblemType, OntologyEntry] = {}
    paths = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
    for path in paths:
        entry = load_ontology_entry(path)
        if entry.problem_type in entries:
            raise ValueError(
                f"Duplicate problem_type '{entry.problem_type.value}' in ontology "
                f"directory: already defined in '{directory}'"
            )
        entries[entry.problem_type] = entry

    return entries

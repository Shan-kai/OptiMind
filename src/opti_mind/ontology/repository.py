"""Ontology repository: YAML-only source of truth for problem templates.

The repository loads entries exclusively from YAML files under
``config/ontology/`` or a user-supplied directory.  Built-in builders have been
removed as part of the single-source ontology rework (see
``a1_baseline_report.md`` and ``a0_gap_trigger_decision.md``).
"""

from __future__ import annotations

from pathlib import Path

from opti_mind.ontology.loader import load_ontology_directory, load_ontology_entry
from opti_mind.ontology.models import OntologyEntry, ProblemType

# Default location for ontology YAML files, relative to this source file:
# src/opti_mind/ontology/repository.py -> project root -> config/ontology
DEFAULT_ONTOLOGY_DIR = Path(__file__).resolve().parents[3] / "config" / "ontology"


class OntologyRepository:
    """In-memory ontology repository backed by YAML files.

    Supports:
    - get(problem_type): exact lookup
    - list_types(): list all registered problem types
    - search(keywords): keyword search across description, tags, variables
    - register(entry): add a custom ontology entry
    - register_from_file(path): load and register an entry from YAML
    """

    def __init__(self, ontology_dir: str | Path | None = None) -> None:
        self._entries: dict[ProblemType, OntologyEntry] = {}

        dir_path = Path(ontology_dir) if ontology_dir is not None else DEFAULT_ONTOLOGY_DIR
        if dir_path.is_dir():
            self._entries.update(load_ontology_directory(dir_path))

    def get(self, problem_type: ProblemType) -> OntologyEntry:
        """Retrieve an ontology entry by problem type."""
        if problem_type not in self._entries:
            raise KeyError(f"Problem type not in ontology: {problem_type}")
        return self._entries[problem_type]

    def list_types(self) -> list[ProblemType]:
        """List all registered problem types."""
        return list(self._entries.keys())

    def search(self, keywords: str) -> list[OntologyEntry]:
        """Search ontology entries by keyword match.

        Matches against description, tags, variable names, and constraint names.
        """
        terms = keywords.lower().split()
        results: list[OntologyEntry] = []
        for entry in self._entries.values():
            haystack = " ".join(
                [
                    entry.description,
                    " ".join(entry.tags),
                    " ".join(v.name for v in entry.variables),
                    " ".join(c.name for c in entry.constraints),
                ]
            ).lower()
            if all(term in haystack for term in terms):
                results.append(entry)
        return results

    def register(self, entry: OntologyEntry) -> None:
        """Register a custom ontology entry."""
        self._entries[entry.problem_type] = entry

    def register_from_file(self, path: str | Path) -> None:
        """Load and register an ontology entry from a YAML file."""
        entry = load_ontology_entry(path)
        self._entries[entry.problem_type] = entry

"""Tests for OntologyRepository."""

from __future__ import annotations

from pathlib import Path

import pytest

from opti_mind.ontology.models import (
    ObjectiveSense,
    OntologyEntry,
    ProblemType,
    VariableKind,
)
from opti_mind.ontology.repository import OntologyRepository

_FACILITY_LOCATION_YAML = """
problem_type: facility_location
description: YAML facility location override
sets:
  I: set of customers
  J: set of facilities
parameters:
  c_ij: cost
variables:
  - name: x_ij
    kind: binary
    description: assignment
    indices:
      - I
      - J
constraints:
  - name: assignment
    expression: sum_{j in J} x_ij
    sense: "=="
    rhs: "1"
    scope: for all i in I
objective:
  sense: minimize
  expression: sum c_ij * x_ij
  description: minimize cost
tags:
  - location
"""

_TRANSPORTATION_YAML = """
problem_type: transportation
description: YAML transportation override
variables:
  - name: x_ij
    kind: continuous
    description: flow
    indices:
      - I
      - J
constraints: []
objective:
  sense: minimize
  expression: sum c_ij * x_ij
"""

_SCHEDULING_YAML = """
problem_type: scheduling
description: scheduling from file
variables: []
constraints: []
"""


def test_builtin_entries_loaded() -> None:
    """Repository loads facility_location, assignment, transportation by default."""
    repo = OntologyRepository()
    registered = repo.list_types()
    assert ProblemType.FACILITY_LOCATION in registered
    assert ProblemType.ASSIGNMENT in registered
    assert ProblemType.TRANSPORTATION in registered


def test_get_facility_location() -> None:
    """Facility location entry has expected sets, variables, constraints."""
    repo = OntologyRepository()
    entry = repo.get(ProblemType.FACILITY_LOCATION)
    assert "I" in entry.sets
    assert "J" in entry.sets
    var_names = {v.name for v in entry.variables}
    assert "x_ij" in var_names
    assert "y_j" in var_names
    assert entry.objective is not None
    assert entry.objective.sense == ObjectiveSense.MINIMIZE


def test_get_assignment() -> None:
    """Assignment entry has one-to-one constraints."""
    repo = OntologyRepository()
    entry = repo.get(ProblemType.ASSIGNMENT)
    constraint_names = {c.name for c in entry.constraints}
    assert "one_task_per_agent" in constraint_names
    assert "one_agent_per_task" in constraint_names


def test_get_transportation() -> None:
    """Transportation entry has supply and demand constraints."""
    repo = OntologyRepository()
    entry = repo.get(ProblemType.TRANSPORTATION)
    constraint_names = {c.name for c in entry.constraints}
    assert "supply" in constraint_names
    assert "demand" in constraint_names
    assert entry.variables[0].kind == VariableKind.CONTINUOUS


def test_all_seven_problem_types_registered() -> None:
    """All 7 problem types from ROADMAP are registered and loadable."""
    repo = OntologyRepository()
    expected_types = [
        ProblemType.FACILITY_LOCATION,
        ProblemType.ASSIGNMENT,
        ProblemType.TRANSPORTATION,
        ProblemType.KNAPSACK,
        ProblemType.NETWORK_FLOW,
        ProblemType.SCHEDULING,
        ProblemType.INVENTORY,
    ]
    registered = repo.list_types()
    for pt in expected_types:
        assert pt in registered, f"Problem type {pt} not registered"
        entry = repo.get(pt)
        assert entry.problem_type == pt
        assert entry.variables, f"{pt} has no variables"
        assert entry.constraints, f"{pt} has no constraints"
        assert entry.objective, f"{pt} has no objective"


def test_search_by_keyword() -> None:
    """Search finds entries matching keywords in description/tags/variables."""
    repo = OntologyRepository()
    results = repo.search("facility location")
    assert len(results) >= 1
    assert any(r.problem_type == ProblemType.FACILITY_LOCATION for r in results)


def test_search_by_tag() -> None:
    """Search finds entries by tag."""
    repo = OntologyRepository()
    results = repo.search("binary")
    assert len(results) >= 2


def test_search_no_match() -> None:
    """Search returns empty list when no entries match."""
    repo = OntologyRepository()
    results = repo.search("nonexistent_problem_xyz")
    assert results == []


def test_register_custom_entry() -> None:
    """Can register and retrieve a custom ontology entry."""
    repo = OntologyRepository()
    custom = OntologyEntry(
        problem_type=ProblemType.KNAPSACK,
        description="0/1 knapsack problem",
        tags=["knapsack", "binary"],
    )
    repo.register(custom)
    assert ProblemType.KNAPSACK in repo.list_types()
    retrieved = repo.get(ProblemType.KNAPSACK)
    assert retrieved.description == "0/1 knapsack problem"


def test_yaml_overrides_default(tmp_path: Path) -> None:
    """YAML entries in the configured directory override the default ontology."""
    (tmp_path / "facility_location.yaml").write_text(_FACILITY_LOCATION_YAML, encoding="utf-8")
    repo = OntologyRepository(ontology_dir=tmp_path)

    entry = repo.get(ProblemType.FACILITY_LOCATION)
    assert entry.description == "YAML facility location override"
    assert entry.variables[0].kind == VariableKind.BINARY


def test_missing_yaml_type_not_loaded(tmp_path: Path) -> None:
    """Only YAML files present in the directory are loaded."""
    (tmp_path / "transportation.yaml").write_text(_TRANSPORTATION_YAML, encoding="utf-8")
    repo = OntologyRepository(ontology_dir=tmp_path)

    transportation = repo.get(ProblemType.TRANSPORTATION)
    assert transportation.description == "YAML transportation override"

    assert ProblemType.FACILITY_LOCATION not in repo.list_types()


def test_default_dir_is_loaded() -> None:
    """The default config/ontology directory is loaded when no custom dir is given."""
    repo = OntologyRepository()
    assert ProblemType.FACILITY_LOCATION in repo.list_types()
    assert ProblemType.KNAPSACK in repo.list_types()


def test_register_from_file(tmp_path: Path) -> None:
    """register_from_file loads a YAML entry into the repository."""
    path = tmp_path / "scheduling.yaml"
    path.write_text(_SCHEDULING_YAML, encoding="utf-8")

    repo = OntologyRepository()
    repo.register_from_file(path)

    entry = repo.get(ProblemType.SCHEDULING)
    assert entry.description == "scheduling from file"


def test_register_from_file_invalid_raises(tmp_path: Path) -> None:
    """register_from_file raises ValueError for invalid YAML content."""
    path = tmp_path / "bad.yaml"
    path.write_text("not: a: valid ontology", encoding="utf-8")

    repo = OntologyRepository()
    with pytest.raises(ValueError):
        repo.register_from_file(path)

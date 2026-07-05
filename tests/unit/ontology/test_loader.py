"""Tests for ontology YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from opti_mind.ontology.loader import load_ontology_directory, load_ontology_entry
from opti_mind.ontology.models import (
    ConstraintSense,
    ObjectiveSense,
    ProblemType,
    VariableKind,
)

_VALID_KNAPSACK_YAML = """
problem_type: knapsack
description: 0/1 knapsack loaded from YAML
sets:
  I: set of items
parameters:
  v_i: value of item i
  w_i: weight of item i
  C: knapsack capacity
variables:
  - name: x_i
    kind: binary
    description: 1 if item i is selected
    indices:
      - I
constraints:
  - name: capacity
    expression: sum_{i in I} w_i * x_i
    sense: "<="
    rhs: C
    description: total weight within capacity
objective:
  sense: maximize
  expression: sum_{i in I} v_i * x_i
  description: maximize total value
tags:
  - knapsack
  - binary
"""


def test_load_ontology_entry_parses_enums_and_structure(tmp_path: Path) -> None:
    """A valid YAML file is converted into a fully populated OntologyEntry."""
    path = tmp_path / "knapsack.yaml"
    path.write_text(_VALID_KNAPSACK_YAML, encoding="utf-8")

    entry = load_ontology_entry(path)

    assert entry.problem_type == ProblemType.KNAPSACK
    assert entry.description == "0/1 knapsack loaded from YAML"
    assert entry.sets == {"I": "set of items"}
    assert entry.parameters == {
        "v_i": "value of item i",
        "w_i": "weight of item i",
        "C": "knapsack capacity",
    }

    assert len(entry.variables) == 1
    var = entry.variables[0]
    assert var.name == "x_i"
    assert var.kind == VariableKind.BINARY
    assert var.indices == ["I"]

    assert len(entry.constraints) == 1
    constraint = entry.constraints[0]
    assert constraint.name == "capacity"
    assert constraint.sense == ConstraintSense.LE
    assert constraint.rhs == "C"

    assert entry.objective is not None
    assert entry.objective.sense == ObjectiveSense.MAXIMIZE
    assert entry.objective.expression == "sum_{i in I} v_i * x_i"

    assert entry.tags == ["knapsack", "binary"]


def test_load_ontology_directory_loads_all_files(tmp_path: Path) -> None:
    """All YAML files in a directory are loaded and keyed by ProblemType."""
    (tmp_path / "knapsack.yaml").write_text(_VALID_KNAPSACK_YAML, encoding="utf-8")
    (tmp_path / "assignment.yaml").write_text(
        """
problem_type: assignment
description: assignment from YAML
variables: []
constraints: []
""",
        encoding="utf-8",
    )

    entries = load_ontology_directory(tmp_path)

    assert set(entries.keys()) == {ProblemType.KNAPSACK, ProblemType.ASSIGNMENT}
    assert entries[ProblemType.KNAPSACK].description == "0/1 knapsack loaded from YAML"


def test_load_ontology_entry_missing_file(tmp_path: Path) -> None:
    """Loading a non-existent file raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        load_ontology_entry(tmp_path / "missing.yaml")


def test_load_ontology_entry_empty_file(tmp_path: Path) -> None:
    """An empty YAML file raises ValueError."""
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_ontology_entry(path)


def test_load_ontology_entry_invalid_yaml_syntax(tmp_path: Path) -> None:
    """Malformed YAML raises ValueError."""
    path = tmp_path / "bad.yaml"
    path.write_text("problem_type: knapsack\n  bad_indent: value", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid YAML"):
        load_ontology_entry(path)


def test_load_ontology_entry_invalid_content(tmp_path: Path) -> None:
    """YAML that does not describe a valid OntologyEntry raises ValueError."""
    path = tmp_path / "invalid.yaml"
    path.write_text(
        "problem_type: not_a_problem\nvariables: []\nconstraints: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid ontology content"):
        load_ontology_entry(path)


def test_load_ontology_directory_not_found(tmp_path: Path) -> None:
    """Loading from a missing directory raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        load_ontology_directory(tmp_path / "does_not_exist")


def test_load_ontology_directory_duplicate_problem_type(tmp_path: Path) -> None:
    """Two YAML files defining the same problem_type raise ValueError."""
    (tmp_path / "a.yaml").write_text(
        "problem_type: knapsack\nvariables: []\nconstraints: []\n",
        encoding="utf-8",
    )
    (tmp_path / "b.yaml").write_text(
        "problem_type: knapsack\nvariables: []\nconstraints: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate"):
        load_ontology_directory(tmp_path)

"""Tests for ontology models."""

from opti_mind.ontology.models import (
    ConstraintSense,
    ConstraintTemplate,
    ObjectiveSense,
    ObjectiveTemplate,
    OntologyEntry,
    ProblemType,
    VariableKind,
    VariableTemplate,
)


def test_variable_template_creation() -> None:
    """VariableTemplate stores name, kind, indices correctly."""
    v = VariableTemplate(
        name="x_ij",
        kind=VariableKind.BINARY,
        description="assignment variable",
        indices=["I", "J"],
    )
    assert v.name == "x_ij"
    assert v.kind == VariableKind.BINARY
    assert v.indices == ["I", "J"]


def test_constraint_template_creation() -> None:
    """ConstraintTemplate stores expression, sense, scope correctly."""
    c = ConstraintTemplate(
        name="demand",
        expression="sum_{i} x_ij",
        sense=ConstraintSense.GE,
        rhs="d_j",
        scope="for all j in J",
    )
    assert c.sense == ConstraintSense.GE
    assert c.rhs == "d_j"


def test_objective_template_creation() -> None:
    """ObjectiveTemplate stores sense and expression."""
    o = ObjectiveTemplate(
        sense=ObjectiveSense.MINIMIZE,
        expression="sum c_ij * x_ij",
    )
    assert o.sense == ObjectiveSense.MINIMIZE


def test_ontology_entry_creation() -> None:
    """OntologyEntry bundles sets, parameters, variables, constraints, objective."""
    entry = OntologyEntry(
        problem_type=ProblemType.FACILITY_LOCATION,
        description="test",
        sets={"I": "customers", "J": "facilities"},
        parameters={"d_i": "demand"},
        variables=[],
        constraints=[],
        tags=["test"],
    )
    assert entry.problem_type == ProblemType.FACILITY_LOCATION
    assert "I" in entry.sets

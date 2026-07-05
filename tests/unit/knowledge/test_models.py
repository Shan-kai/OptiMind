"""Tests for knowledge models."""

from opti_mind.knowledge.models import KnowledgePackage, ProblemSpecification
from opti_mind.ontology.models import (
    ObjectiveSense,
    ObjectiveTemplate,
    OntologyEntry,
    ProblemType,
    VariableKind,
    VariableTemplate,
)


def test_problem_specification_creation() -> None:
    """ProblemSpecification stores problem type and available fields."""
    spec = ProblemSpecification(
        problem_type=ProblemType.FACILITY_LOCATION,
        available_fields=["demand", "capacity", "cost"],
        business_context="Choose facility locations",
    )
    assert spec.problem_type == ProblemType.FACILITY_LOCATION
    assert len(spec.available_fields) == 3
    assert spec.business_context == "Choose facility locations"


def test_knowledge_package_creation() -> None:
    """KnowledgePackage stores ontology entry and matched fields."""
    entry = OntologyEntry(
        problem_type=ProblemType.FACILITY_LOCATION,
        description="Test entry",
        variables=[
            VariableTemplate(
                name="x_ij",
                kind=VariableKind.BINARY,
                description="Test variable",
            )
        ],
        objective=ObjectiveTemplate(
            sense=ObjectiveSense.MINIMIZE,
            expression="sum c_ij * x_ij",
        ),
    )
    pkg = KnowledgePackage(
        problem_type=ProblemType.FACILITY_LOCATION,
        ontology_entry=entry,
        variables=entry.variables,
        objective=entry.objective,
        matched_fields={"c_ij": "cost"},
        confidence=0.9,
    )
    assert pkg.problem_type == ProblemType.FACILITY_LOCATION
    assert len(pkg.variables) == 1
    assert pkg.matched_fields["c_ij"] == "cost"
    assert pkg.confidence == 0.9

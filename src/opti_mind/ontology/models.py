"""Optimization Ontology models.

Defines the knowledge base entries for each optimization problem type:
variables, constraints, objectives, and the full problem template.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class VariableKind(StrEnum):
    """Kind of decision variable."""

    BINARY = "binary"
    INTEGER = "integer"
    CONTINUOUS = "continuous"


class ConstraintSense(StrEnum):
    """Constraint direction."""

    LE = "<="
    GE = ">="
    EQ = "=="


class ObjectiveSense(StrEnum):
    """Objective direction."""

    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class ProblemType(StrEnum):
    """Supported optimization problem types."""

    FACILITY_LOCATION = "facility_location"
    ASSIGNMENT = "assignment"
    TRANSPORTATION = "transportation"
    KNAPSACK = "knapsack"
    NETWORK_FLOW = "network_flow"
    SCHEDULING = "scheduling"
    INVENTORY = "inventory"


class VariableTemplate(BaseModel):
    """Template for a decision variable in a problem type."""

    name: str = Field(description="Symbolic name, e.g. 'x_ij'")
    kind: VariableKind
    description: str = Field(description="Human-readable description")
    indices: list[str] = Field(
        default_factory=list,
        description="Index sets this variable is defined over, e.g. ['I', 'J']",
    )
    lower_bound: float | None = None
    upper_bound: float | None = None


class ConstraintTemplate(BaseModel):
    """Template for a constraint in a problem type."""

    name: str = Field(description="Constraint identifier")
    expression: str = Field(description="Symbolic expression")
    sense: ConstraintSense
    rhs: str = Field(default="0", description="Right-hand side expression")
    scope: str = Field(
        default="",
        description="Quantifier scope, e.g. 'for all i in I'",
    )
    description: str = ""


class ObjectiveTemplate(BaseModel):
    """Template for the objective function."""

    sense: ObjectiveSense
    expression: str = Field(description="Symbolic expression to optimize")
    description: str = ""


class OntologyEntry(BaseModel):
    """A complete optimization problem template in the ontology.

    Bundles together all the building blocks (variables, constraints,
    objective, sets, parameters) needed to model a given problem type.
    """

    problem_type: ProblemType
    description: str = ""
    sets: dict[str, str] = Field(
        default_factory=dict,
        description="Set definitions: name -> description",
    )
    parameters: dict[str, str] = Field(
        default_factory=dict,
        description="Parameter definitions: symbol -> description",
    )
    variables: list[VariableTemplate] = Field(default_factory=list)
    constraints: list[ConstraintTemplate] = Field(default_factory=list)
    objective: ObjectiveTemplate | None = None
    tags: list[str] = Field(default_factory=list)

    # Single-source schema extensions (see docs/specs/ONTOLOGY_SPEC.md)
    signature: dict[str, Any] = Field(
        default_factory=dict,
        description="Problem signature: index_roles, required_roles, optional_roles, etc.",
    )
    aliases: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Symbol aliases: base or short name -> list of aliases",
    )
    defaults: dict[str, Any] = Field(
        default_factory=dict,
        description="Default values for parameters keyed by base symbol",
    )
    logic_checks: dict[str, Any] = Field(
        default_factory=dict,
        description="Structural logic checks for validation",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProblemSpecification(BaseModel):
    """Specification of an optimization problem to be solved.

    Captures the problem type, available data fields, and any hints about
    the modeling intent. This is the input to knowledge retrieval.
    """

    problem_type: ProblemType = Field(description="Identified optimization problem type")
    available_fields: list[str] = Field(
        default_factory=list,
        description="Column names / data fields available from the dataset",
    )
    business_context: str = Field(
        default="",
        description="Optional business context or natural language description",
    )
    constraints_hint: list[str] = Field(
        default_factory=list,
        description="Optional hints about required constraints",
    )
    objective_hint: str = Field(
        default="",
        description="Optional hint about the optimization objective",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgePackage(BaseModel):
    """Retrieved knowledge package for modeling.

    Contains all the building blocks needed to construct an optimization
    model: variables, constraints, objective, and the full ontology entry.
    This is the output of knowledge retrieval and input to model generation.
    """

    problem_type: ProblemType
    ontology_entry: OntologyEntry = Field(description="Full ontology entry for the problem type")
    variables: list[VariableTemplate] = Field(
        default_factory=list,
        description="Decision variable templates",
    )
    constraints: list[ConstraintTemplate] = Field(
        default_factory=list,
        description="Constraint templates",
    )
    objective: ObjectiveTemplate | None = Field(
        default=None,
        description="Objective function template",
    )
    matched_fields: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from ontology parameters to available data fields",
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence score of the retrieval (0.0 to 1.0)",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Retrieval notes or warnings",
    )

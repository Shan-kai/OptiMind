"""IR models: the Intermediate Representation per IR_SPEC.

These pydantic models form the universal data contract between all layers.
See docs/specs/IR_SPEC.md for the spec.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


class IRSet(BaseModel):
    """An index set in the optimization model."""

    name: str = Field(description="Set name, e.g. 'I'")
    description: str = ""
    index_domain: str = Field(default="int", description="Domain of indices")
    members: str | list[Any] = Field(
        default="from_instance",
        description="Either 'from_instance' or explicit list",
    )


class IRParameter(BaseModel):
    """A known parameter value in the optimization model."""

    name: str = Field(description="Parameter symbol, e.g. 'd_i'")
    description: str = ""
    sets: list[str] = Field(default_factory=list, description="Index sets")
    dtype: str = Field(default="float", description="Data type")
    source: str = Field(default="", description="Traceability: feature_map:col->sym")


class IRVariable(BaseModel):
    """A decision variable in the optimization model."""

    name: str = Field(description="Variable symbol, e.g. 'x_ij'")
    description: str = ""
    sets: list[str] = Field(default_factory=list, description="Index sets")
    domain: str = Field(
        default="continuous",
        description="binary / integer / continuous / semi_continuous",
    )
    lower: float | None = None
    upper: float | None = None


class IRExpressionTerm(BaseModel):
    """A single term in a linear/quadratic expression."""

    coef: str = Field(description="Coefficient symbol or literal, e.g. 'f_j' or '1'")
    var: str = Field(description="Variable symbol, e.g. 'x_ij'")
    sum_sets: list[str] = Field(
        default_factory=list,
        description="Sets to sum over, e.g. ['J']",
    )
    where: str = Field(
        default="",
        description="Condition, e.g. 'i in I'",
    )


class IRExpression(BaseModel):
    """An objective or constraint expression."""

    kind: str = Field(
        default="linear",
        description="linear / quadratic / general",
    )
    terms: list[IRExpressionTerm] = Field(default_factory=list)
    raw_expr: str = Field(
        default="",
        description="Symbolic expression when terms decomposition is not applicable",
    )
    latex: str = Field(
        default="",
        description="LaTeX rendering of the expression for the frontend",
    )


class IRConstraint(BaseModel):
    """A single constraint in the optimization model."""

    name: str = Field(description="Constraint identifier")
    expr: str = Field(description="Symbolic expression, e.g. 'sum_{j in J} x_ij'")
    scope: str = Field(default="", description="Quantifier scope, e.g. 'forall i in I'")
    sense: str = Field(
        default="le",
        description="le (<=) / ge (>=) / eq (==) / range",
    )
    rhs: str | None = Field(
        default=None,
        description="Right-hand side expression, or null if in expr",
    )
    description: str = ""
    latex: str = Field(
        default="",
        description="LaTeX rendering of the full constraint for the frontend",
    )


class IRModel(BaseModel):
    """The full Intermediate Representation of an optimization model."""

    meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata: schema_version, source problem spec, etc.",
    )
    problem_type: str = Field(description="Problem type, e.g. 'facility_location'")
    sense: str = Field(default="minimize", description="minimize / maximize")
    sets: list[IRSet] = Field(default_factory=list)
    parameters: list[IRParameter] = Field(default_factory=list)
    variables: list[IRVariable] = Field(default_factory=list)
    objective: IRExpression | None = None
    constraints: list[IRConstraint] = Field(default_factory=list)

    def model_dump_safe(self) -> dict[str, Any]:
        """Dump to a JSON-serializable dict with schema_version always set."""
        data = self.model_dump()
        data.setdefault("meta", {})
        data["meta"]["schema_version"] = SCHEMA_VERSION
        return data

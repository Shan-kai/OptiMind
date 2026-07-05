"""Gap report: structured contract between workflow stations and ontology patching.

A ``GapReport`` is produced by any workflow station when the deterministic
path cannot fully resolve the ontology requirements. It is consumed by
``IOntologyService.patch_for`` to produce a structured ``OntologyPatch``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class GapKind(StrEnum):
    """Kind of gap that triggered the report."""

    PROBLEM_TYPE_UNCERTAIN = "problem_type_uncertain"
    REQUIRED_ROLES_MISSING = "required_roles_missing"
    REQUIRED_PARAMETERS_MISSING = "required_parameters_missing"
    IR_VALIDATION_FAILED = "ir_validation_failed"
    COMBINED = "combined"


class GapReport(BaseModel):
    """Serializable gap report used to request an ontology patch.

    Mirrors the contract defined in ``a0_gap_trigger_decision.md``.  The patch
    layer must never receive raw natural language; all context is encoded here.
    """

    # Trigger source
    trigger_station: Literal["data_intelligence", "modeling", "verification"]
    gap_kind: GapKind
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence of the deterministic path at trigger time",
    )

    # Problem-type identification
    detected_problem_type: str | None = None
    problem_type_candidates: list[str] = Field(
        default_factory=list,
        description="Candidate problem types ordered by confidence",
    )

    # Schema / role gap
    missing_roles: list[str] = Field(
        default_factory=list,
        description="Canonical roles required but not present",
    )
    present_roles: list[str] = Field(default_factory=list)
    column_aliases_tried: list[str] = Field(
        default_factory=list,
        description="Keyword/alias completion attempts already applied",
    )

    # Parameter gap
    missing_parameters: list[str] = Field(
        default_factory=list,
        description="Ontology parameter symbols still missing",
    )
    inferred_parameters: list[str] = Field(
        default_factory=list,
        description="Parameters already inferred by deterministic heuristics",
    )

    # Validation gap
    validation_failures: list[str] = Field(
        default_factory=list,
        description="Human-readable failure details from verification",
    )

    # Patch recommendation
    recommended_action: Literal[
        "proceed",
        "clarify",
        "patch",
        "abort",
    ] = Field(
        default="patch",
        description="Recommended workflow action for this gap",
    )
    recommended_patch_kind: (
        Literal[
            "ontology_extension",
            "schema_remap",
            "parameter_completion",
            "set_completion",
            "problem_type_clarify",
        ]
        | None
    ) = None

    # Tracing
    upstream_attempts: int = Field(
        default=0,
        ge=0,
        description="How many deterministic->patch loops have already run",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of report creation",
    )

    def bump_attempt(self) -> GapReport:
        """Return a copy with ``upstream_attempts`` incremented by one."""
        return self.model_copy(update={"upstream_attempts": self.upstream_attempts + 1})

"""Ontology service models, protocol and reference implementation.

This module defines the public data contract of ``OntologyService``:
``IOntologyService`` Protocol, request/response models, and the structured
patch schema. Keeping models here lets API, workflow, and chat layers import
them without pulling in additional implementation details.
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from opti_mind.config import get_settings
from opti_mind.data.models import DataProfileReport, FieldSemantics, OptimizationInstance
from opti_mind.ontology.gap_report import GapKind, GapReport
from opti_mind.ontology.models import (
    KnowledgePackage,
    OntologyEntry,
    ProblemSpecification,
    ProblemType,
)
from opti_mind.ontology.repository import OntologyRepository

logger = logging.getLogger(__name__)


class ParameterShape(StrEnum):
    """Allowed shapes for an ontology parameter."""

    SCALAR = "scalar"
    VECTOR = "vector"
    MATRIX = "matrix"
    TENSOR = "tensor"


class ValidationSeverity(StrEnum):
    """Severity of a validation finding."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class SetInfo(BaseModel):
    """Self-describing set metadata exposed by the ontology service."""

    name: str = Field(description="Set symbol, e.g. 'I'")
    description: str = ""
    index_roles: list[str] = Field(
        default_factory=list,
        description="Canonical roles that typically populate this set",
    )


class ParameterInfo(BaseModel):
    """Self-describing parameter metadata exposed by the ontology service."""

    symbol: str = Field(description="Full symbol, e.g. 'd_i'")
    base_name: str = Field(description="Base parameter name, e.g. 'd'")
    description: str = ""
    aliases: list[str] = Field(default_factory=list, description="Common column-name aliases")
    shape: ParameterShape = ParameterShape.SCALAR
    index_sets: list[str] = Field(default_factory=list, description="Index sets, e.g. ['I']")
    required: bool = True
    default_value: Any | None = None
    default_formula: str | None = None
    dtype: str = "float"


class VariableInfo(BaseModel):
    """Self-describing variable metadata exposed by the ontology service."""

    name: str
    description: str = ""
    kind: str = Field(description="binary / integer / continuous")
    index_sets: list[str] = Field(default_factory=list)
    lower_bound: float | None = None
    upper_bound: float | None = None


class ConstraintInfo(BaseModel):
    """Self-describing constraint metadata exposed by the ontology service."""

    name: str
    description: str = ""
    expression: str
    sense: str
    rhs: str
    scope: str = ""


class ObjectiveInfo(BaseModel):
    """Self-describing objective metadata exposed by the ontology service."""

    sense: str
    expression: str
    description: str = ""


class ProblemTypeInfo(BaseModel):
    """Lightweight problem type item used by ``GET /problem-types`` lists."""

    value: str = Field(description="Problem type value, e.g. 'facility_location'")
    label: str = Field(description="Human-readable label")
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class ProblemTypeDetail(BaseModel):
    """Full self-describing metadata returned by ``GET /problem-types/{value}``."""

    value: str = Field(description="Problem type value, e.g. 'facility_location'")
    label: str = Field(description="Human-readable label")
    description: str = ""
    sets: dict[str, SetInfo] = Field(default_factory=dict)
    parameters: list[ParameterInfo] = Field(default_factory=list)
    variables: list[VariableInfo] = Field(default_factory=list)
    constraints: list[ConstraintInfo] = Field(default_factory=list)
    objective: ObjectiveInfo | None = None
    tags: list[str] = Field(default_factory=list)


class DetectionResult(BaseModel):
    """Result of ontology-driven problem-type detection."""

    problem_type: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    candidates: list[tuple[str, float]] = Field(
        default_factory=list,
        description="Candidate types with scores, ordered by confidence",
    )
    matched_roles: list[str] = Field(default_factory=list)
    missing_roles: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)


class FieldMatchResult(BaseModel):
    """Result of matching available columns to ontology parameters/roles."""

    problem_type: str
    matched_fields: dict[str, str] = Field(
        default_factory=dict,
        description="Ontology parameter symbol -> matched column name",
    )
    unmatched_parameters: list[str] = Field(default_factory=list)
    unmatched_roles: list[str] = Field(default_factory=list)
    role_mappings: dict[str, str] = Field(
        default_factory=dict,
        description="Column name -> canonical role",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class ValidationFinding(BaseModel):
    """Single finding from ``IOntologyService.validate``."""

    severity: ValidationSeverity
    code: str
    message: str
    parameter: str | None = None
    role: str | None = None


class ValidationResult(BaseModel):
    """Result of validating an instance against an ontology entry."""

    passed: bool
    findings: list[ValidationFinding] = Field(default_factory=list)
    missing_required_parameters: list[str] = Field(default_factory=list)
    missing_required_roles: list[str] = Field(default_factory=list)


class RoleMappingPatch(BaseModel):
    """A single column -> canonical role remapping proposed by a patch."""

    column: str
    canonical_role: str
    reason: str = ""


class ParameterPatch(BaseModel):
    """A single parameter value/fallback proposed by a patch."""

    symbol: str
    value: Any | None = None
    formula: str | None = None
    reason: str = ""


class SetPatch(BaseModel):
    """A single set extension proposed by a patch."""

    name: str
    members: list[Any] = Field(default_factory=list)
    reason: str = ""


class OntologyExtensionPatch(BaseModel):
    """A single ontology-level extension proposed by a patch."""

    kind: Literal["variable", "constraint", "parameter", "set"]
    name: str
    definition: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class OntologyPatch(BaseModel):
    """Structured patch produced by ``IOntologyService.patch_for``.

    A patch is **never** a full ``IRModel``. It only describes deterministic
    mutations that downstream code can apply and audit.

    Approval semantics are driven by ``confidence``:
    - ``confidence >= 0.9``: auto-apply, no summary needed.
    - ``0.7 <= confidence < 0.9``: auto-apply, but surface ``show_summary``.
    - ``confidence < 0.7``: require human approval.
    """

    problem_type: str
    gap_kind: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    role_mappings: list[RoleMappingPatch] = Field(default_factory=list)
    parameter_patches: list[ParameterPatch] = Field(
        default_factory=list,
        description="Default values or formulas for missing parameters",
    )
    set_patches: list[SetPatch] = Field(
        default_factory=list,
        description="Additional set members to inject",
    )
    ontology_extensions: list[OntologyExtensionPatch] = Field(
        default_factory=list,
        description="New variables/constraints/parameters/sets",
    )
    problem_type_suggestion: str | None = None

    reasoning: list[str] = Field(default_factory=list)
    show_summary: bool = Field(
        default=False,
        description="Whether to display a summary even when auto-applied",
    )


class PatchApplicationResult(BaseModel):
    """Outcome of applying a patch to an instance."""

    success: bool
    applied_patch: OntologyPatch | None = None
    updated_instance: OptimizationInstance | None = None
    errors: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class OntologyServiceConfig:
    """Runtime knobs for ``OntologyService`` heuristic behavior.

    These values are intentionally hardcoded as service defaults; they can be
    overridden via ``WorkflowDependencies`` when needed.
    """

    theta_type: float = 0.4
    theta_required_role_missing: int = 1  # any missing required role triggers
    theta_param_missing_count: int = 1  # any missing required parameter triggers
    max_upstream_attempts: int = 2
    show_summary_confidence_threshold: float = 0.7
    approval_confidence_threshold: float = 0.9


@runtime_checkable
class IOntologyService(Protocol):
    """Public contract for ontology-driven detection, retrieval and patching.

    ``IOntologyService`` is intended to replace ``IKnowledgeRetriever`` in the
    workflow layer. It is the single source of truth for:

    - problem type detection and signatures,
    - ontology retrieval and self-description,
    - deterministic validation against ontology,
    - structured ontology patching (never direct IR generation).
    """

    def list_types(self) -> list[ProblemTypeInfo]:
        """Return all registered problem types (lightweight list view)."""
        ...

    def get_entry(self, problem_type: str) -> OntologyEntry | None:
        """Return the raw ontology entry for a problem type, or ``None``."""
        ...

    def get_detail(self, problem_type: str) -> ProblemTypeDetail | None:
        """Return full self-describing metadata for a problem type, or ``None``."""
        ...

    def detect(
        self,
        columns: list[str],
        profile: DataProfileReport | None = None,
        semantics: list[FieldSemantics] | None = None,
        business_context: str = "",
        hint: str | None = None,
    ) -> DetectionResult:
        """Detect the most likely problem type from data/schema hints."""
        ...

    def match_fields(
        self,
        problem_type: str,
        columns: list[str],
        semantics: list[FieldSemantics] | None = None,
    ) -> FieldMatchResult:
        """Match available columns to ontology parameters and canonical roles."""
        ...

    def retrieve(self, problem_spec: ProblemSpecification) -> KnowledgePackage:
        """Retrieve the ontology knowledge package for a problem specification."""
        ...

    def validate(
        self,
        problem_type: str,
        instance: dict[str, Any] | None = None,
        ir: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate an instance or IR dict against ontology requirements."""
        ...

    def aliases(
        self,
        symbol: str,
        problem_type: str | None = None,
    ) -> list[str]:
        """Return known aliases for an ontology parameter symbol."""
        ...

    def patch_for(
        self,
        gap: GapReport,
        instance: dict[str, Any] | None = None,
        field_semantics: list[FieldSemantics] | None = None,
        business_goal: str = "",
    ) -> OntologyPatch:
        """Produce a structured ontology patch for a reported gap.

        Implementations must **not** return a full ``IRModel``. The patch is
        applied deterministically by the workflow layer, then the normal
        deterministic IR generation path is rerun.
        """
        ...

    def apply_patch(
        self,
        patch: OntologyPatch,
        instance: dict[str, Any],
    ) -> PatchApplicationResult:
        """Deterministically apply an approved patch to an instance dict."""
        ...


def compute_patch_approval(confidence: float, cfg: OntologyServiceConfig) -> dict[str, bool]:
    """Compute approval flags for a patch from its confidence score.

    Returns a dict with ``requires_approval`` and ``show_summary`` following the
    A0/A2 graded policy.
    """
    return {
        "requires_approval": confidence < cfg.approval_confidence_threshold,
        "show_summary": confidence >= cfg.show_summary_confidence_threshold
        and confidence < cfg.approval_confidence_threshold,
    }


# Heuristic column-name keyword hints used when ontology metadata does not
# already provide a match. These are intentionally conservative; they will be
# migrated into ontology YAML aliases over time.
_KEYWORD_HINTS: dict[str, list[str]] = {
    "customer_key": ["customer", "cust"],
    "facility_key": ["facility", "warehouse", "site"],
    "agent_key": ["agent", "worker", "employee"],
    "task_key": ["task", "job"],
    "source_key": ["source", "origin", "from"],
    "sink_key": ["sink", "destination", "to", "dest"],
    "demand": ["demand", "qty", "quantity", "requirement"],
    "supply": ["supply", "stock", "available"],
    "capacity": ["capacity", "cap", "limit"],
    "fixed_cost": ["fixed_cost", "opening_cost", "fixed"],
    "cost": ["cost", "shipping_cost", "transport_cost", "distance"],
    "value": ["value", "profit", "benefit"],
    "weight": ["weight", "mass", "size"],
    "processing_time": ["processing_time", "duration", "ptime"],
    "due_date": ["due_date", "deadline"],
    "holding_cost": ["holding_cost", "holding", "storage"],
    "ordering_cost": ["ordering_cost", "setup_cost", "ordering"],
    "purchase_cost": ["purchase_cost", "unit_cost"],
    "initial_inventory": ["initial_inventory", "opening_inventory"],
}


def _shape_default(symbol: str, instance: OptimizationInstance, scalar: Any) -> Any:
    """Shape a scalar ontology default to the symbol's index structure."""
    if "_" not in symbol:
        return scalar

    subscript = symbol.split("_", 1)[1]
    index_sets = [ch.upper() for ch in subscript if ch.isalpha() and ch.upper() in instance.sets]
    if not index_sets:
        return scalar

    if len(index_sets) == 1:
        return {str(member): scalar for member in instance.sets[index_sets[0]]}

    return _nested_default(instance, index_sets, scalar)


def _nested_default(
    instance: OptimizationInstance,
    index_sets: list[str],
    scalar: Any,
) -> dict[str, Any]:
    """Build a nested dict default for multi-index parameters."""
    first, *rest = index_sets
    result: dict[str, Any] = {}
    for member in instance.sets[first]:
        key = str(member)
        if rest:
            result[key] = _nested_default(instance, rest, scalar)
        else:
            result[key] = scalar
    return result


def shape_default(symbol: str, instance: OptimizationInstance, scalar: Any) -> Any:
    """Shape a scalar ontology default to the symbol's index structure."""
    if "_" not in symbol:
        return scalar

    subscript = symbol.split("_", 1)[1]
    index_sets = [ch.upper() for ch in subscript if ch.isalpha() and ch.upper() in instance.sets]
    if not index_sets:
        return scalar

    if len(index_sets) == 1:
        return {str(member): scalar for member in instance.sets[index_sets[0]]}

    return nested_default(instance, index_sets, scalar)


def nested_default(
    instance: OptimizationInstance,
    index_sets: list[str],
    scalar: Any,
) -> dict[str, Any]:
    """Build a nested dict default for multi-index parameters."""
    first, *rest = index_sets
    result: dict[str, Any] = {}
    for member in instance.sets[first]:
        key = str(member)
        if rest:
            result[key] = nested_default(instance, rest, scalar)
        else:
            result[key] = scalar
    return result


class OntologyService:
    """Reference implementation of :class:`IOntologyService`."""

    def __init__(
        self,
        repository: OntologyRepository | None = None,
        match_threshold: float | None = None,
    ) -> None:
        self._repository = repository or OntologyRepository()
        self._match_threshold = (
            match_threshold
            if match_threshold is not None
            else (get_settings().knowledge_match_threshold)
        )

    def list_types(self) -> list[ProblemTypeInfo]:
        """Return lightweight summaries for all registered problem types."""
        infos: list[ProblemTypeInfo] = []
        for problem_type in self._repository.list_types():
            entry = self._repository.get(problem_type)
            infos.append(
                ProblemTypeInfo(
                    value=problem_type.value,
                    label=problem_type.value.replace("_", " ").title(),
                    description=entry.description.split("\n")[0].strip(),
                    tags=entry.tags,
                )
            )
        return sorted(infos, key=lambda x: x.label)

    def get_entry(self, problem_type: str) -> OntologyEntry | None:
        """Return the ontology entry for a problem type, or ``None``."""
        try:
            return self._repository.get(ProblemType(problem_type))
        except Exception:  # noqa: BLE001
            return None

    def get_detail(self, problem_type: str) -> ProblemTypeDetail | None:
        """Return full self-describing metadata for a problem type."""
        entry = self.get_entry(problem_type)
        if entry is None:
            return None

        sig = entry.signature or {}
        index_roles: dict[str, list[str]] = {}
        for role, set_name in zip(
            sig.get("index_roles", []),
            list(entry.sets.keys()),
            strict=False,
        ):
            index_roles.setdefault(set_name, []).append(role)

        sets = {
            name: SetInfo(name=name, description=desc, index_roles=index_roles.get(name, []))
            for name, desc in entry.sets.items()
        }

        required_params = set(sig.get("required_parameters", []))
        parameters: list[ParameterInfo] = []
        for symbol, desc in entry.parameters.items():
            base = symbol.split("_", 1)[0] if "_" in symbol else symbol
            subscript = symbol.split("_", 1)[1] if "_" in symbol else ""
            index_sets = [ch.upper() for ch in subscript if ch.isalpha()]
            shape = ParameterShape.SCALAR
            if len(index_sets) == 1:
                shape = ParameterShape.VECTOR
            elif len(index_sets) >= 2:
                shape = ParameterShape.MATRIX
            parameters.append(
                ParameterInfo(
                    symbol=symbol,
                    base_name=base,
                    description=desc,
                    aliases=entry.aliases.get(base, []),
                    shape=shape,
                    index_sets=index_sets,
                    required=symbol in required_params,
                    default_value=entry.defaults.get(base),
                    dtype="float",
                )
            )

        variables = [
            VariableInfo(
                name=v.name,
                description=v.description,
                kind=v.kind.value,
                index_sets=v.indices,
                lower_bound=v.lower_bound,
                upper_bound=v.upper_bound,
            )
            for v in entry.variables
        ]

        constraints = [
            ConstraintInfo(
                name=c.name,
                description=c.description,
                expression=c.expression,
                sense=c.sense.value,
                rhs=c.rhs,
                scope=c.scope,
            )
            for c in entry.constraints
        ]

        objective = None
        if entry.objective is not None:
            objective = ObjectiveInfo(
                sense=entry.objective.sense.value,
                expression=entry.objective.expression,
                description=entry.objective.description,
            )

        return ProblemTypeDetail(
            value=problem_type,
            label=problem_type.replace("_", " ").title(),
            description=entry.description,
            sets=sets,
            parameters=parameters,
            variables=variables,
            constraints=constraints,
            objective=objective,
            tags=entry.tags,
        )

    def detect(
        self,
        columns: list[str],
        profile: DataProfileReport | None = None,
        semantics: list[FieldSemantics] | None = None,
        business_context: str = "",
        hint: str | None = None,
    ) -> DetectionResult:
        """Detect the problem type from column names and optional semantics."""
        del profile, business_context  # reserved for future use

        if semantics is None:
            semantics = []

        present_roles = {s.semantic_role for s in semantics if s.semantic_role}
        present_roles.update(
            s.canonical_role.value for s in semantics if s.canonical_role is not None
        )
        column_names = {c.lower() for c in columns}

        scored: list[tuple[ProblemType, float]] = []
        for problem_type in self._repository.list_types():
            entry = self._repository.get(problem_type)
            sig = entry.signature or {}
            required = set(sig.get("required_roles", []))
            optional = set(sig.get("optional_roles", []))

            matched_required = {r for r in required if r in present_roles}
            matched_optional = {r for r in optional if r in present_roles}

            keyword_score = 0.0
            if not matched_required and not matched_optional:
                keyword_score = self._keyword_score(problem_type.value, column_names)

            if required:
                confidence = (
                    len(matched_required) / len(required) * 0.6
                    + len(matched_optional) / max(len(optional), 1) * 0.2
                    + keyword_score * 0.2
                )
            else:
                confidence = 0.5 + keyword_score * 0.5

            if hint and problem_type.value == hint and matched_required:
                confidence = min(1.0, confidence + 0.2)

            confidence = min(1.0, max(0.0, confidence))
            scored.append((problem_type, round(confidence, 3)))

        scored.sort(key=lambda x: x[1], reverse=True)
        best_type, best_confidence = scored[0] if scored else (None, 0.0)

        candidates = [(pt.value, conf) for pt, conf in scored[:3]]
        missing_roles: list[str] = []
        if best_type is not None:
            sig = self._repository.get(best_type).signature or {}
            required = set(sig.get("required_roles", []))
            missing_roles = sorted(required - present_roles)

        return DetectionResult(
            problem_type=best_type.value if best_type else None,
            confidence=best_confidence,
            candidates=candidates,
            matched_roles=sorted(present_roles),
            missing_roles=missing_roles,
            reasoning=[f"best match based on {len(present_roles)} present roles"],
        )

    def _keyword_score(self, problem_type: str, column_names: set[str]) -> float:
        """Return a keyword overlap score between 0 and 1."""
        try:
            entry = self._repository.get(ProblemType(problem_type))
        except Exception:  # noqa: BLE001
            return 0.0
        sig = entry.signature or {}
        roles = list(sig.get("required_roles", [])) + list(sig.get("optional_roles", []))
        if not roles:
            return 0.0
        hits = 0
        for role in roles:
            hints = _KEYWORD_HINTS.get(role, [role])
            if any(any(h in col for h in hints) for col in column_names):
                hits += 1
        return hits / len(roles)

    def match_fields(
        self,
        problem_type: str,
        columns: list[str],
        semantics: list[FieldSemantics] | None = None,
    ) -> FieldMatchResult:
        """Match data columns to ontology roles and parameter symbols."""
        entry = self.get_entry(problem_type)
        if entry is None:
            return FieldMatchResult(
                problem_type=problem_type,
                notes=[f"Unknown problem type: {problem_type}"],
                confidence=0.0,
            )

        sig = entry.signature or {}
        all_roles = set(sig.get("required_roles", [])) | set(sig.get("optional_roles", []))

        role_mappings: dict[str, str] = {}
        matched_fields: dict[str, str] = {}
        matched_columns: set[str] = set()

        for sem in semantics or []:
            role = sem.canonical_role.value if sem.canonical_role else (sem.semantic_role or "")
            if role and role in all_roles:
                role_mappings[sem.column] = role
                symbol = self._role_to_symbol(role, entry)
                if symbol:
                    matched_fields[symbol] = sem.column
                matched_columns.add(sem.column)

        unmatched_roles = sorted(all_roles - set(role_mappings.values()))
        unmatched_parameters = sorted(set(entry.parameters.keys()) - set(matched_fields.keys()))
        unmatched_columns = [c for c in columns if c not in matched_columns]

        # Confidence: fraction of required roles matched.
        required = set(sig.get("required_roles", []))
        confidence = 1.0
        if required:
            matched_required = {r for r in required if r in set(role_mappings.values())}
            confidence = len(matched_required) / len(required)

        notes: list[str] = []
        if unmatched_parameters:
            notes.append(f"Unmatched parameters: {', '.join(unmatched_parameters)}")
        if unmatched_columns:
            notes.append(f"Unmatched columns: {', '.join(unmatched_columns[:5])}")

        return FieldMatchResult(
            problem_type=problem_type,
            matched_fields=matched_fields,
            unmatched_parameters=unmatched_parameters,
            unmatched_roles=unmatched_roles,
            role_mappings=role_mappings,
            confidence=round(confidence, 3),
            notes=notes,
        )

    @staticmethod
    def _role_to_symbol(role: str, entry: OntologyEntry) -> str | None:
        """Map a canonical role to the most likely parameter symbol."""
        role_symbol_hints: dict[str, str] = {
            "demand": "d_i",
            "supply": "s_i",
            "capacity": "Q_j",
            "fixed_cost": "f_j",
            "cost": "c_ij",
            "distance": "c_ij",
            "value": "v_i",
            "weight": "w_i",
            "processing_time": "p_j",
            "due_date": "d_j",
            "weight_priority": "w_j",
            "holding_cost": "h_i",
            "ordering_cost": "s_i",
            "purchase_cost": "c_i",
            "initial_inventory": "I0_i",
        }
        hint = role_symbol_hints.get(role)
        if hint and hint in entry.parameters:
            return hint
        for symbol, desc in entry.parameters.items():
            if role.replace("_", " ") in desc.lower():
                return symbol
        return None

    def retrieve(self, problem_spec: ProblemSpecification) -> KnowledgePackage:
        """Retrieve a knowledge package for the given problem specification."""
        entry = self._repository.get(problem_spec.problem_type)
        matched_fields = self._match_parameters(entry, problem_spec.available_fields)
        notes: list[str] = []
        unmatched_params = set(entry.parameters.keys()) - set(matched_fields.keys())
        if unmatched_params:
            notes.append(
                f"Unmatched parameters: {', '.join(sorted(unmatched_params))}. "
                "Model generation may need default values or user input."
            )

        match_ratio = len(matched_fields) / max(len(entry.parameters), 1)
        confidence = round(0.5 + 0.5 * match_ratio, 3)
        if problem_spec.business_context:
            confidence = min(1.0, round(confidence + 0.05, 3))

        return KnowledgePackage(
            problem_type=problem_spec.problem_type,
            ontology_entry=entry,
            variables=list(entry.variables),
            constraints=list(entry.constraints),
            objective=entry.objective,
            matched_fields=matched_fields,
            confidence=confidence,
            notes=notes,
        )

    def _match_parameters(
        self, entry: OntologyEntry, available_fields: list[str]
    ) -> dict[str, str]:
        """Match ontology parameters to available data fields."""
        matched: dict[str, str] = {}
        fields_lower = [f.lower() for f in available_fields]
        matched_field_names: set[str] = set()

        for param_name in entry.parameters:
            hints = self._param_hints(entry, param_name)
            for hint in hints:
                for field_name, field_lower in zip(available_fields, fields_lower, strict=False):
                    if param_name in matched:
                        break
                    if field_name in matched_field_names:
                        continue
                    if hint in field_lower:
                        matched[param_name] = field_name
                        matched_field_names.add(field_name)
                        break
                if param_name in matched:
                    break

        # Fuzzy fallback for remaining parameters.
        for param_name in entry.parameters:
            if param_name in matched:
                continue
            hints = self._param_hints(entry, param_name)
            for hint in hints:
                best_ratio = 0.0
                best_field: str | None = None
                for field_name, field_lower in zip(available_fields, fields_lower, strict=False):
                    if field_name in matched_field_names:
                        continue
                    ratio = difflib.SequenceMatcher(None, hint, field_lower).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_field = field_name
                if best_field and best_ratio >= self._match_threshold:
                    matched[param_name] = best_field
                    matched_field_names.add(best_field)
                    break

        return matched

    @staticmethod
    def _param_hints(entry: OntologyEntry, param_name: str) -> list[str]:
        """Build a list of matching hints for a parameter."""
        hints: list[str] = []
        desc = (entry.parameters.get(param_name) or "").lower()
        hints.extend([h.strip() for h in desc.split() if len(h.strip()) > 2])
        for alias, symbols in (entry.aliases or {}).items():
            if param_name in symbols:
                hints.append(alias)
        base = param_name.split("_", 1)[0] if "_" in param_name else param_name
        hints.append(base)
        return hints

    def validate(
        self,
        problem_type: str,
        instance: dict[str, Any] | None = None,
        ir: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate an instance or IR dict against ontology requirements."""
        entry = self.get_entry(problem_type)
        if entry is None:
            return ValidationResult(
                passed=False,
                findings=[
                    ValidationFinding(
                        severity=ValidationSeverity.ERROR,
                        code="unknown_problem_type",
                        message=f"Problem type not in ontology: {problem_type}",
                    )
                ],
            )

        findings: list[ValidationFinding] = []
        missing_params: list[str] = []
        missing_roles: list[str] = []
        sig = entry.signature or {}

        if instance is not None:
            opt_instance = OptimizationInstance.model_validate(instance)
            required_params = set(sig.get("required_parameters", []))
            present = set(opt_instance.parameters.keys())
            present_bases = {p.split("_", 1)[0] for p in present if "_" in p}
            present_bases.update(p for p in present if "_" not in p)
            for rp in required_params:
                base = rp.split("_", 1)[0] if "_" in rp else rp
                if rp not in present and base not in present_bases:
                    missing_params.append(rp)
                    findings.append(
                        ValidationFinding(
                            severity=ValidationSeverity.ERROR,
                            code="missing_required_parameter",
                            message=f"Missing required parameter: {rp}",
                            parameter=rp,
                        )
                    )

            required_sets = set(sig.get("required_sets", []))
            for rs in required_sets:
                if rs not in opt_instance.sets or not opt_instance.sets[rs]:
                    findings.append(
                        ValidationFinding(
                            severity=ValidationSeverity.ERROR,
                            code="missing_required_set",
                            message=f"Missing or empty required set: {rs}",
                        )
                    )

        if ir is not None:
            if ir.get("problem_type") != problem_type:
                findings.append(
                    ValidationFinding(
                        severity=ValidationSeverity.ERROR,
                        code="problem_type_mismatch",
                        message="IR problem_type mismatch",
                    )
                )
            variables = ir.get("variables") or []
            required_vars = set(sig.get("required_variables", []))
            present_vars = {v.get("name") for v in variables if isinstance(v, dict)}
            for rv in required_vars - present_vars:
                findings.append(
                    ValidationFinding(
                        severity=ValidationSeverity.ERROR,
                        code="missing_required_variable",
                        message=f"Missing required variable: {rv}",
                    )
                )

        return ValidationResult(
            passed=not findings,
            findings=findings,
            missing_required_parameters=missing_params,
            missing_required_roles=missing_roles,
        )

    def aliases(
        self,
        symbol: str,
        problem_type: str | None = None,
    ) -> list[str]:
        """Return aliases for a symbol, optionally scoped to a problem type."""
        if problem_type is None:
            return [symbol]
        entry = self.get_entry(problem_type)
        if entry is None:
            return [symbol]
        aliases = entry.aliases or {}
        if symbol in aliases:
            return aliases[symbol]
        base = symbol.split("_", 1)[0] if "_" in symbol else symbol
        if base in aliases:
            return aliases[base]
        return [symbol]

    def patch_for(
        self,
        gap: GapReport,
        instance: dict[str, Any] | None = None,
        field_semantics: list[FieldSemantics] | None = None,
        business_goal: str = "",
    ) -> OntologyPatch:
        """Generate an ontology patch for the given gap report.

        This reference implementation performs deterministic parameter completion
        using ontology defaults when possible. Future iterations can call an LLM
        here while still only emitting ontology-level patches (never IR).
        """
        del field_semantics, business_goal  # reserved for future LLM context

        problem_type = gap.detected_problem_type or ""
        entry = self.get_entry(problem_type) if problem_type else None

        if gap.gap_kind == GapKind.REQUIRED_PARAMETERS_MISSING and gap.missing_parameters:
            patches: list[ParameterPatch] = []
            for symbol in gap.missing_parameters:
                base = symbol.split("_", 1)[0] if "_" in symbol else symbol
                default_value: Any | None = None
                if entry is not None and base in entry.defaults:
                    default_value = entry.defaults[base]
                    if instance is not None:
                        try:
                            opt_instance = OptimizationInstance.model_validate(instance)
                            default_value = shape_default(symbol, opt_instance, default_value)
                        except Exception:  # noqa: BLE001
                            pass
                if default_value is not None:
                    patches.append(
                        ParameterPatch(
                            symbol=symbol,
                            value=default_value,
                            reason=f"Filled from ontology default for '{base}'",
                        )
                    )
            if patches:
                return OntologyPatch(
                    problem_type=problem_type,
                    gap_kind=gap.gap_kind,
                    confidence=0.95,
                    parameter_patches=patches,
                    reasoning=["Deterministic parameter completion from ontology defaults"],
                    show_summary=False,
                )
            return OntologyPatch(
                problem_type=problem_type,
                gap_kind=gap.gap_kind,
                confidence=0.3,
                parameter_patches=[],
                reasoning=[
                    f"No ontology default available for missing parameters: "
                    f"{', '.join(gap.missing_parameters)}. User input is required."
                ],
                show_summary=True,
            )

        return OntologyPatch(
            problem_type=problem_type,
            gap_kind=gap.gap_kind,
            confidence=0.5,
            reasoning=[f"No deterministic patch available for {gap.gap_kind}"],
        )

    def apply_patch(
        self,
        patch: OntologyPatch,
        instance: dict[str, Any],
    ) -> PatchApplicationResult:
        """Deterministically apply an approved patch to an instance dict."""
        errors: list[str] = []
        try:
            opt_instance = OptimizationInstance.model_validate(instance)
        except Exception as exc:  # noqa: BLE001
            return PatchApplicationResult(
                success=False,
                errors=[f"Invalid instance: {exc}"],
            )

        for pp in patch.parameter_patches:
            if pp.value is not None:
                opt_instance.parameters[pp.symbol] = pp.value
            elif pp.formula is not None:
                errors.append(f"Formula patches not yet supported: {pp.symbol}")

        for sp in patch.set_patches:
            opt_instance.sets.setdefault(sp.name, []).extend(sp.members)

        if errors:
            return PatchApplicationResult(
                success=False,
                applied_patch=patch,
                updated_instance=opt_instance,
                errors=errors,
            )

        return PatchApplicationResult(
            success=True,
            applied_patch=patch,
            updated_instance=opt_instance,
        )

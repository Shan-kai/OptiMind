"""Pydantic models describing the Data Intelligence Layer outputs."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    """Single-column statistics produced by the DataProfiler."""

    name: str
    dtype: str
    missing_rate: float = Field(ge=0.0, le=1.0)
    non_null_count: int
    unique_count: int
    cardinality: float = Field(ge=0.0, le=1.0)
    min_value: Any | None = None
    max_value: Any | None = None
    quantiles: dict[str, float] = Field(default_factory=dict)
    value_range: tuple[Any | None, Any | None] | None = None


class DataProfileReport(BaseModel):
    """Aggregated profile over all columns of a dataset."""

    n_rows: int
    n_cols: int
    columns: list[ColumnProfile]


class QualityIssue(BaseModel):
    """A single data-quality finding."""

    column: str
    kind: str
    detail: str = ""


class QualityReport(BaseModel):
    """Output of the DataQualityChecker."""

    issues: list[QualityIssue] = Field(default_factory=list)
    passed: bool = True


class CanonicalRole(StrEnum):
    CUSTOMER_KEY = "customer_key"
    FACILITY_KEY = "facility_key"
    AGENT_KEY = "agent_key"
    TASK_KEY = "task_key"
    SOURCE_KEY = "source_key"
    SINK_KEY = "sink_key"
    DEMAND = "demand"
    SUPPLY = "supply"
    CAPACITY = "capacity"
    FIXED_COST = "fixed_cost"
    COST = "cost"
    DISTANCE = "distance"
    VALUE = "value"
    WEIGHT = "weight"
    PROCESSING_TIME = "processing_time"
    DUE_DATE = "due_date"
    HOLDING_COST = "holding_cost"
    ORDERING_COST = "ordering_cost"
    PURCHASE_COST = "purchase_cost"
    INITIAL_INVENTORY = "initial_inventory"
    BALANCE = "balance"
    IGNORE = "ignore"
    OTHER = "other"


class FieldSemantics(BaseModel):
    """Schema understanding result per column."""

    column: str
    semantic_role: str | None = None
    optimization_symbol: str | None = None
    confidence: float = 1.0
    canonical_role: CanonicalRole | None = None
    is_index: bool = False


class FieldMappingProposal(BaseModel):
    """A single column's proposed mapping produced by the LLM mapping agent."""

    column: str
    semantic_role: str | None = None
    optimization_symbol: str | None = None
    canonical_role: CanonicalRole | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    chinese_label: str = ""
    reasoning: str = ""
    is_index: bool = False

    def to_field_semantics(self) -> FieldSemantics:
        """Convert the proposal to the canonical FieldSemantics model."""
        return FieldSemantics(
            column=self.column,
            semantic_role=self.semantic_role,
            optimization_symbol=self.optimization_symbol,
            confidence=self.confidence,
            canonical_role=self.canonical_role,
            is_index=self.is_index,
        )


class SchemaMappingProposal(BaseModel):
    """Full mapping proposal for an uploaded dataset."""

    problem_type: str | None = None
    fields: list[FieldMappingProposal] = Field(default_factory=list)
    overall_reasoning: str = ""

    def to_field_semantics_list(self) -> list[FieldSemantics]:
        """Convert all proposals to FieldSemantics, preserving order."""
        return [f.to_field_semantics() for f in self.fields]

    def get_field(self, column: str) -> FieldMappingProposal | None:
        """Return the proposal for a given column name."""
        for field in self.fields:
            if field.column == column:
                return field
        return None


class OptimizationInstance(BaseModel):
    """Standardized input to the Optimization Intelligence Layer."""

    problem_type: str
    sets: dict[str, list[Any]] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)

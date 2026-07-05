"""Decision intelligence models and data structures."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VariableSummary(BaseModel):
    """Summary of a single variable in the solution."""

    name: str
    value: float | dict[str, float]
    description: str = ""
    is_indexed: bool = False


class ConstraintStatus(BaseModel):
    """Status of a constraint in the solution."""

    name: str
    lhs_value: float | None = None
    rhs_value: float | None = None
    slack: float | None = None
    is_binding: bool = False
    is_violated: bool = False


class SensitivityResult(BaseModel):
    """Sensitivity analysis result for a parameter."""

    parameter_name: str
    current_value: float
    allowable_increase: float | None = None
    allowable_decrease: float | None = None
    shadow_price: float | None = None
    interpretation: str = ""


class ScenarioComparison(BaseModel):
    """Comparison between baseline and a scenario."""

    scenario_name: str
    baseline_objective: float | None = None
    scenario_objective: float | None = None
    objective_delta: float | None = None
    objective_delta_pct: float | None = None
    key_changes: list[str] = Field(default_factory=list)
    recommendation: str = ""


class RiskItem(BaseModel):
    """A single risk item in the risk assessment."""

    category: str
    severity: str
    description: str
    mitigation: str = ""


class Recommendation(BaseModel):
    """A business recommendation derived from the solution."""

    category: str
    priority: str
    title: str
    description: str
    expected_impact: str = ""
    actionable: bool = True


class AnalysisReport(BaseModel):
    """Complete decision intelligence report."""

    status: str
    objective_value: float | None = None
    objective_sense: str = "minimize"
    variable_summaries: list[VariableSummary] = Field(default_factory=list)
    constraint_statuses: list[ConstraintStatus] = Field(default_factory=list)
    sensitivity_results: list[SensitivityResult] = Field(default_factory=list)
    scenario_comparisons: list[ScenarioComparison] = Field(default_factory=list)
    risk_items: list[RiskItem] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    executive_summary: str = ""
    raw_solution: dict[str, Any] = Field(default_factory=dict)

    # LLM-augmented narrative insights (optional enhancement).
    llm_summary: str = ""
    llm_recommendations: list[str] = Field(default_factory=list)
    llm_assumptions: list[str] = Field(default_factory=list)

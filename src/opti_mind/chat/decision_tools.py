"""Tool definitions for the LLM-driven decision analysis agent.

These tools let an LLM answer post-solution questions by reading the existing
report, running sensitivity analysis, or executing what-if scenarios through the
deterministic decision engines. They never mutate the original model or solution.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from opti_mind.chat.types import ToolDefinition


class ExplainSolutionInput(BaseModel):
    """Explain the current solution and report in business terms."""

    pass


class AnalyzeSensitivityInput(BaseModel):
    """Return sensitivity analysis for one or all parameters."""

    parameter_name: str | None = Field(
        default=None,
        description="Optional parameter symbol (e.g. 'c_ij'). Omit to return all parameters.",
    )


class RunScenarioInput(BaseModel):
    """Run a what-if scenario by modifying parameters and re-solving."""

    changes: list[str] = Field(
        default_factory=list,
        description="List of parameter changes, e.g. ['c_ij *= 1.1', 'Q_j += 10'].",
    )
    name: str | None = Field(
        default=None,
        description="Optional scenario name. If omitted, a default name is generated.",
    )


class SummarizeReportInput(BaseModel):
    """Summarize the full analysis report, including recommendations and risks."""

    pass


class AskUserInput(BaseModel):
    """Ask the user for clarification when the question is ambiguous."""

    question: str = Field(description="Concise Chinese question to show the user.")


DECISION_TOOL_DEFINITIONS: list[ToolDefinition] = [
    ToolDefinition(
        name="explain_solution",
        description="Explain the solver solution and key metrics in business terms.",
        input_schema=ExplainSolutionInput.model_json_schema(),
    ),
    ToolDefinition(
        name="analyze_sensitivity",
        description="Analyze sensitivity of the solution to one or all parameters.",
        input_schema=AnalyzeSensitivityInput.model_json_schema(),
    ),
    ToolDefinition(
        name="run_scenario",
        description="Run a what-if scenario by modifying parameters and re-solving.",
        input_schema=RunScenarioInput.model_json_schema(),
    ),
    ToolDefinition(
        name="summarize_report",
        description="Summarize the full analysis report including recommendations and risks.",
        input_schema=SummarizeReportInput.model_json_schema(),
    ),
    ToolDefinition(
        name="ask_user",
        description="Ask the user a clarifying question when the request is ambiguous.",
        input_schema=AskUserInput.model_json_schema(),
    ),
]


def execute_decision_tool_call(tool_call: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Convenience wrapper that creates a default executor and runs one tool call."""
    from opti_mind.chat.decision_tool_executor import DecisionToolExecutor

    executor = DecisionToolExecutor()
    return executor.execute(tool_call, state)

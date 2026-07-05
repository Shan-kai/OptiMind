"""Clarification request model for the human-in-the-loop mini-agent.

When a pipeline station cannot confidently proceed (e.g. a required semantic
role is missing from the schema interpretation, a critical model parameter
has no matching data field, or an ontology patch needs user approval), it
builds a ClarificationRequest and the workflow emits it via
langgraph.types.interrupt(), pausing until the user resumes.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ClarificationOption(BaseModel):
    """A selectable option shown to the user during clarification."""

    label: str = Field(description="Short human-readable label, e.g. a column name")
    value: str = Field(description="Machine value to feed back, e.g. the column to use")


class ClarificationRequest(BaseModel):
    """A request for human input raised by a pipeline station."""

    station: Literal["data_intelligence", "modeling", "ontology_patch"] = Field(
        description="Pipeline station that raised the request"
    )
    question: str = Field(description="The question to ask the user in natural language")
    options: list[ClarificationOption] = Field(
        default_factory=list,
        description="Selectable options; empty means a free-text answer is expected",
    )
    expected_field: str = Field(
        description="Field/parameter this answer resolves",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra context key/value pairs to help the user decide",
    )


class ClarificationResponse(BaseModel):
    """The user's answer to a ClarificationRequest, fed back via resume."""

    station: Literal["data_intelligence", "modeling", "ontology_patch"]
    expected_field: str
    answer: str = Field(description="The selected option value or free-text answer")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Copied from the original ClarificationRequest for context",
    )

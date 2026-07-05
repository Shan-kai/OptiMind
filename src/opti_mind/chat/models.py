"""Chat layer models for the conversational OptiMind frontend."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single message in the session chat history."""

    role: str = Field(
        ...,
        description="Message role: system, assistant, or user",
    )
    content: str = Field(..., description="Message text")
    created_at: str | None = Field(
        default=None,
        description="ISO timestamp when the message was created",
    )

    @classmethod
    def create(cls, role: str, content: str) -> ChatMessage:
        """Factory that stamps the current UTC time."""
        return cls(
            role=role,
            content=content,
            created_at=datetime.now(UTC).isoformat(),
        )


class ChatAction(BaseModel):
    """Structured action produced by ChatAgent from a user message."""

    action: str = Field(
        ...,
        description=(
            "One of: answer_clarification, set_business_goal, "
            "set_problem_type, set_source, run_pipeline, chat"
        ),
    )
    answer: str = Field(
        default="",
        description="Answer to a pending clarification",
    )
    field: str = Field(
        default="",
        description="Which state field to update (for set_* actions)",
    )
    value: str = Field(
        default="",
        description="New value for the field (for set_* actions)",
    )
    message: str = Field(
        default="",
        description="Direct reply to the user when no state change is needed",
    )

    def model_post_init(self, __context: Any) -> None:
        """Normalize action names."""
        self.action = self.action.strip().lower()


class ChatActionResult(BaseModel):
    """Result returned by the agentic field-mapping loop.

    This is the richer counterpart of ChatAction: it carries both the assistant
    message to display and any state updates / pipeline continuation flags that
    the session layer must apply.
    """

    final_message: str = Field(default="", description="Assistant message shown to the user.")
    state_updates: dict[str, Any] = Field(
        default_factory=dict,
        description="Values to write into the workflow checkpoint.",
    )
    continue_pipeline: bool = Field(
        default=False,
        description="If True, the caller should run the rest of the pipeline.",
    )
    pending_clarification: dict[str, Any] | None = Field(
        default=None,
        description="Optional legacy clarification request to surface to the UI.",
    )
    events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Observable events produced during the agent loop.",
    )


class ChatRequest(BaseModel):
    """User message sent to an existing session."""

    message: str = Field(..., description="User's natural-language message")


class SessionResponse(BaseModel):
    """Response returned for session create/chat/get operations."""

    session_id: str
    status: str = Field(
        ...,
        description="Session status: created, awaiting_input, success, error",
    )
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Chat history for this session",
    )
    clarification_request: dict[str, Any] | None = Field(
        default=None,
        description="Pending clarification request, if status is awaiting_input",
    )
    analysis_report: dict[str, Any] | None = None
    execution_graph: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    ir: dict[str, Any] | None = Field(
        default=None, description="Final modeling IR (verified_ir preferred, fallback ir)"
    )
    solution: dict[str, Any] | None = Field(
        default=None, description="Solver solution with status, objective_value and variables"
    )
    instance: dict[str, Any] | None = Field(
        default=None, description="Optimization instance with sets and input parameters"
    )

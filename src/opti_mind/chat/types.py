"""Internal protocol types for the conversational agent layer.

These types mirror Pi's ``AgentMessage`` / ``AgentEvent`` protocol: they are
structured, serializable, and used throughout the agent loop and session layer.
Conversion to LLM-specific dicts happens only at the LLM boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """Description of a tool available to the LLM."""

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCall(BaseModel):
    """A single tool call emitted by the LLM."""

    tool: str = Field(description="Name of the tool to invoke.")
    input: dict[str, Any] = Field(default_factory=dict, description="Tool arguments.")


class AgentMessage(BaseModel):
    """A single message in an agent conversation.

    This is the internal representation used by :class:`AgentLoop` and
    :class:`AgentSession`. It is richer than the API-facing ``ChatMessage``
    because it also carries tool results and metadata.
    """

    role: Literal["system", "user", "assistant", "tool"] = Field(
        ..., description="Message role in the agent conversation."
    )
    content: str = Field(..., description="Text content of the message.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra metadata, e.g. tool name, timestamp, model info.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO timestamp when the message was created.",
    )

    @classmethod
    def create(
        cls,
        role: Literal["system", "user", "assistant", "tool"],
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        """Factory that stamps the current UTC time."""
        return cls(role=role, content=content, metadata=metadata or {})

    def to_llm_message(self) -> dict[str, Any]:
        """Convert to a plain dict accepted by the LLM client."""
        return {"role": self.role, "content": self.content}


class AgentEvent(BaseModel):
    """A single lifecycle event emitted by an AgentLoop."""

    type: Literal[
        "message_delta",
        "tool_start",
        "tool_end",
        "state_update",
        "done",
        "error",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)

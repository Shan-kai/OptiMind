"""Generic Agent Loop and supporting event types.

The AgentLoop is the stable core that drives any tool-using agent:

1. Prepare context from state + chat history + user message.
2. Request the LLM with a system prompt and available tools.
3. Parse the response for assistant messages and tool calls.
4. Emit events so callers can observe progress.
5. Execute tools through a configurable executor with hooks.
6. Accumulate state updates and continue until done or max turns.

This module intentionally has no dependency on FastAPI, LangGraph, or the
optimization domain. Those concerns live in callers.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from opti_mind.chat.i18n import CHAT_STRINGS
from opti_mind.chat.types import AgentEvent, ToolCall
from opti_mind.config import get_settings
from opti_mind.core.llm_client import ILLMClient, create_llm_client

logger = logging.getLogger(__name__)


class AgentLoopResult(BaseModel):
    """Final result returned by an AgentLoop run."""

    final_message: str = Field(default="", description="Assistant message shown to the user.")
    state_updates: dict[str, Any] = Field(
        default_factory=dict,
        description="Values to write into the workflow checkpoint.",
    )
    continue_pipeline: bool = Field(
        default=False,
        description="If True, the caller should run the rest of the pipeline.",
    )
    events: list[AgentEvent] = Field(
        default_factory=list,
        description="Observable events produced during the loop.",
    )


class ToolHooks:
    """Optional hooks invoked around each tool execution.

    Subclass this to add logging, permission gates, parameter scrubbing, or
    audit trails without changing the executor implementation.
    """

    def before_tool_call(
        self,
        tool: str,
        input_data: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Return possibly modified input_data before the tool runs."""
        return input_data

    def after_tool_call(
        self,
        tool: str,
        input_data: dict[str, Any],
        result: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Return possibly modified result after the tool runs."""
        return result


class AgentLoop:
    """A reusable tool-using agent loop.

    Args:
        system_prompt: Prompt shown to the LLM at the start of every run.
        tool_executor: Callable that executes a single tool call dict and
            returns a JSON-serializable result dict.
        llm_client: Optional ILLMClient. If omitted, the shared client is used.
        hooks: Optional ToolHooks subclass for before/after interception.
        max_tool_turns: Maximum number of tool-turn iterations.
    """

    def __init__(
        self,
        system_prompt: str,
        tool_executor: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        llm_client: ILLMClient | None = None,
        hooks: ToolHooks | None = None,
        max_tool_turns: int | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.tool_executor = tool_executor
        self.llm_client = llm_client or create_llm_client()
        self.hooks = hooks or ToolHooks()
        self.max_tool_turns = max_tool_turns or get_settings().llm_orchestrator_max_tool_turns

    def run(
        self,
        state: dict[str, Any],
        chat_history: list[dict[str, Any]],
        user_message: str,
    ) -> AgentLoopResult:
        """Run the loop to completion and return the final result."""
        events: list[AgentEvent] = []
        conversation = self._build_conversation(state, chat_history, user_message)
        accumulated_state_updates: dict[str, Any] = {}

        for _turn in range(self.max_tool_turns):
            messages = [{"role": "system", "content": self.system_prompt}] + conversation
            try:
                response = self.llm_client.chat(messages)
                parsed = self._parse_response(response.content)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Agent loop parsing failed: %s", exc)
                events.append(AgentEvent(type="error", payload={"message": str(exc)}))
                return AgentLoopResult(
                    final_message=CHAT_STRINGS.fallback_not_understood,
                    state_updates=accumulated_state_updates,
                    events=events,
                )

            events.append(
                AgentEvent(
                    type="message_delta",
                    payload={
                        "final_message": parsed.final_message,
                        "tool_calls": [tc.model_dump() for tc in parsed.tool_calls],
                    },
                )
            )

            if parsed.tool_calls:
                conversation.append({"role": "assistant", "content": response.content})
                for tc in parsed.tool_calls:
                    input_data = tc.input
                    events.append(
                        AgentEvent(
                            type="tool_start", payload={"tool": tc.tool, "input": input_data}
                        )
                    )

                    input_data = self.hooks.before_tool_call(tc.tool, input_data, state)
                    tool_result = self.tool_executor({"tool": tc.tool, "input": input_data}, state)
                    tool_result = self.hooks.after_tool_call(
                        tc.tool, input_data, tool_result, state
                    )

                    events.append(
                        AgentEvent(
                            type="tool_end", payload={"tool": tc.tool, "result": tool_result}
                        )
                    )

                    conversation.append(
                        {
                            "role": "user",
                            "content": (
                                f"Tool result for {tc.tool}:\n"
                                f"{json.dumps(tool_result, ensure_ascii=False, indent=2)}"
                            ),
                        }
                    )

                    state_updates = tool_result.get("state_updates", {})
                    if state_updates:
                        events.append(AgentEvent(type="state_update", payload=state_updates))
                        accumulated_state_updates.update(state_updates)
                        state.update(state_updates)

                    if tool_result.get("continue_pipeline"):
                        events.append(
                            AgentEvent(type="done", payload={"reason": "continue_pipeline"})
                        )
                        return AgentLoopResult(
                            final_message=parsed.final_message or "已确认，继续执行后续流程。",
                            state_updates=accumulated_state_updates,
                            continue_pipeline=True,
                            events=events,
                        )
                    if tool_result.get("ask_user"):
                        events.append(AgentEvent(type="done", payload={"reason": "ask_user"}))
                        return AgentLoopResult(
                            final_message=tool_result.get("result", {}).get("question", ""),
                            state_updates=accumulated_state_updates,
                            events=events,
                        )
                    if tool_result.get("requires_pipeline_run"):
                        events.append(
                            AgentEvent(type="done", payload={"reason": "requires_pipeline_run"})
                        )
                        return AgentLoopResult(
                            final_message="我需要先运行数据识别步骤，稍后再填入参数。",
                            state_updates=accumulated_state_updates,
                            continue_pipeline=True,
                            events=events,
                        )
                continue

            events.append(AgentEvent(type="done", payload={"reason": "final_message"}))
            return AgentLoopResult(
                final_message=parsed.final_message,
                state_updates=accumulated_state_updates,
                events=events,
            )

        events.append(AgentEvent(type="done", payload={"reason": "max_turns"}))
        return AgentLoopResult(
            final_message="我已经做了多轮调整，请确认当前状态是否正确，或告诉我需要修改的地方。",
            state_updates=accumulated_state_updates,
            events=events,
        )

    def _build_conversation(
        self,
        state: dict[str, Any],
        chat_history: list[dict[str, Any]],
        user_message: str,
    ) -> list[dict[str, str]]:
        """Build the initial conversation context for the loop."""
        recent = chat_history[-10:] if chat_history else []
        context_message = (
            f"Current state:\n{json.dumps(state, ensure_ascii=False, indent=2)}\n\n"
            f"Recent chat history:\n{json.dumps(recent, ensure_ascii=False, indent=2)}"
        )
        return [
            {"role": "user", "content": context_message},
            {"role": "user", "content": f"User message: {user_message}"},
        ]

    @staticmethod
    def _parse_response(content: str) -> _AgentResponse:
        """Parse the LLM response into final_message + tool_calls.

        Accepts:
        - Bare JSON objects/arrays
        - JSON wrapped in markdown code fences (``` or ```json)
        - Plain text replies (returned as final_message with no tool_calls)
        """
        text = content.strip()
        if not text:
            return _AgentResponse(final_message="", tool_calls=[])

        # Try bare JSON first.
        try:
            data = json.loads(text)
            return AgentLoop._agent_response_from_data(data)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code fences.
        if text.startswith("```"):
            lines = text.split("\n")
            # Drop opening fence line (may include "json").
            start = 1
            if lines[0].strip().startswith("```") and len(lines[0].strip()) > 3:
                start = 1
            # Drop closing fence line if present.
            end = len(lines) - 1 if lines[-1].strip().startswith("```") else len(lines)
            inner = "\n".join(lines[start:end]).strip()
            if inner.startswith("json"):
                inner = inner[4:].strip()
            try:
                data = json.loads(inner)
                return AgentLoop._agent_response_from_data(data)
            except json.JSONDecodeError:
                pass

        # Last resort: look for the first JSON object/array anywhere in the text.
        for start_char, end_char in (("{", "}"), ("[", "]")):
            start_idx = text.find(start_char)
            if start_idx == -1:
                continue
            # Simple bracket matching to find the matching close bracket.
            depth = 0
            in_string = False
            escape = False
            for idx in range(start_idx, len(text)):
                ch = text[idx]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"' and (idx == start_idx or text[idx - 1] != "\\"):
                    in_string = not in_string
                    continue
                if not in_string:
                    if ch == start_char:
                        depth += 1
                    elif ch == end_char:
                        depth -= 1
                        if depth == 0:
                            try:
                                data = json.loads(text[start_idx : idx + 1])
                                return AgentLoop._agent_response_from_data(data)
                            except json.JSONDecodeError:
                                break
                            except Exception:  # noqa: BLE001
                                break

        # Treat as plain text direct reply.
        return _AgentResponse(final_message=text, tool_calls=[])

    @staticmethod
    def _agent_response_from_data(data: Any) -> _AgentResponse:
        """Build an _AgentResponse from parsed JSON data."""
        if isinstance(data, list):
            tool_calls = [ToolCall.model_validate(tc) for tc in data]
            return _AgentResponse(final_message="", tool_calls=tool_calls)
        if isinstance(data, dict):
            return _AgentResponse(
                final_message=data.get("final_message", ""),
                tool_calls=[ToolCall.model_validate(tc) for tc in data.get("tool_calls", [])],
            )
        return _AgentResponse(final_message="", tool_calls=[])


class _AgentResponse(BaseModel):
    """Internal LLM output shape for the agent loop."""

    final_message: str = Field(default="", description="Chinese text to show the user.")
    tool_calls: list[ToolCall] = Field(default_factory=list, description="Tools to invoke.")

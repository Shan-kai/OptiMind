"""Tests for the decision analysis agent."""

from __future__ import annotations

import json
from typing import Any

from opti_mind.chat.decision_agent import DecisionAgent
from opti_mind.core.llm_client import LLMResponse
from opti_mind.decision.models import AnalysisReport


class FakeLLMClientQueue:
    """Fake LLM client returning a queued sequence of JSON responses."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.index = 0

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        del messages, kwargs
        if self.index >= len(self.responses):
            return LLMResponse(
                content=json.dumps({"final_message": "No more responses.", "tool_calls": []}),
                model="fake",
            )
        response = self.responses[self.index]
        self.index += 1
        return LLMResponse(content=response, model="fake")


def _response(final_message: str = "", tool_calls: list[dict[str, Any]] | None = None) -> str:
    return json.dumps(
        {"final_message": final_message, "tool_calls": tool_calls or []},
        ensure_ascii=False,
    )


def test_decision_agent_summarizes_report() -> None:
    """The agent calls summarize_report and returns a Chinese summary."""
    responses = [
        _response(
            final_message="",
            tool_calls=[{"tool": "summarize_report", "input": {}}],
        ),
        _response(
            final_message="目标值为 42.0，建议减少固定成本。",
            tool_calls=[],
        ),
    ]
    agent = DecisionAgent(llm_client=FakeLLMClientQueue(responses))

    state: dict[str, Any] = {
        "solution": {"objective_value": 42.0, "status": "optimal"},
        "report": AnalysisReport(
            status="optimal",
            objective_value=42.0,
            executive_summary="Good solution.",
        ).model_dump(mode="json"),
    }

    result = agent.run(state=state, chat_history=[], user_message="总结一下")

    assert "42.0" in result.final_message
    assert len(result.events) >= 2


def test_decision_agent_runs_scenario() -> None:
    """The agent converts a what-if question into a run_scenario tool call."""
    responses = [
        _response(
            final_message="",
            tool_calls=[{"tool": "run_scenario", "input": {"changes": ["c_ij *= 1.1"]}}],
        ),
        _response(
            final_message="如果 c_ij 增加 10%，目标值会上升 4.2。",
            tool_calls=[],
        ),
    ]
    agent = DecisionAgent(llm_client=FakeLLMClientQueue(responses))

    state: dict[str, Any] = {
        "solution": {"objective_value": 42.0, "status": "optimal"},
        "report": AnalysisReport(status="optimal").model_dump(mode="json"),
    }

    result = agent.run(state=state, chat_history=[], user_message="如果 c_ij 增加 10% 会怎样？")

    assert "4.2" in result.final_message


def test_decision_agent_asks_user_when_ambiguous() -> None:
    """The agent returns a clarifying question when the request is unclear."""
    responses = [
        _response(
            final_message="",
            tool_calls=[{"tool": "ask_user", "input": {"question": "你想分析哪个参数？"}}],
        ),
    ]
    agent = DecisionAgent(llm_client=FakeLLMClientQueue(responses))

    state: dict[str, Any] = {
        "solution": {"objective_value": 42.0},
        "report": AnalysisReport(status="optimal").model_dump(mode="json"),
    }

    result = agent.run(state=state, chat_history=[], user_message="分析一下")

    assert result.final_message == "你想分析哪个参数？"

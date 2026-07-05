"""Tests for the generic AgentLoop."""

from __future__ import annotations

import json
from typing import Any

from opti_mind.chat.agent_loop import AgentLoop
from opti_mind.core.llm_client import ILLMClient, LLMResponse


class _FakeLLM(ILLMClient):
    """LLM client that returns queued responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._calls: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        self._calls.append(messages)
        content = self._responses.pop(0)
        return LLMResponse(content=content)


def _requires_pipeline_executor(
    _tool_call: dict[str, Any], _state: dict[str, Any]
) -> dict[str, Any]:
    """Tool executor that signals the pipeline must run first."""
    return {
        "status": "error",
        "error": "模型实例尚未生成，无法写入参数。",
        "requires_pipeline_run": True,
    }


def test_parse_response_treats_plain_text_as_final_message() -> None:
    """Non-JSON replies should be surfaced to the user instead of throwing."""
    parsed = AgentLoop._parse_response("这是一个纯文本回复。")
    assert parsed.final_message == "这是一个纯文本回复。"
    assert parsed.tool_calls == []


def test_parse_response_handles_markdown_json() -> None:
    """Markdown-wrapped JSON should be extracted and parsed."""
    content = (
        "```json\n"
        + json.dumps({"final_message": "ok", "tool_calls": []}, ensure_ascii=False)
        + "\n```"
    )
    parsed = AgentLoop._parse_response(content)
    assert parsed.final_message == "ok"
    assert parsed.tool_calls == []


def test_requires_pipeline_run_returns_continue_pipeline() -> None:
    """A tool result asking for the pipeline should make the loop exit gracefully."""
    response = json.dumps(
        {
            "final_message": "",
            "tool_calls": [
                {
                    "tool": "provide_parameter",
                    "input": {"symbol": "f_j", "value": [1.0, 8.0]},
                }
            ],
        },
        ensure_ascii=False,
    )
    loop = AgentLoop(
        system_prompt="system",
        tool_executor=_requires_pipeline_executor,
        llm_client=_FakeLLM([response]),
        max_tool_turns=3,
    )

    result = loop.run({}, [], "f_j 为 1,8")

    assert result.continue_pipeline is True
    assert "先运行数据识别" in result.final_message
    assert "抱歉" not in result.final_message

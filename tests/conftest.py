"""Shared test fixtures for OptiMind."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import pytest

# Ensure tests run deterministically and never call a real LLM provider,
# even when the developer has a .env file with live keys.
os.environ["OPTI_MIND_LLM_SCHEMA_INTERPRETER"] = "false"
os.environ["OPTI_MIND_LLM_MODEL_GENERATOR"] = "false"
os.environ["OPTI_MIND_LLM_DECISION_ANALYZER"] = "false"
os.environ["OPTI_MIND_LLM_DECISION_ANALYZER_AGENT"] = "false"
os.environ["OPTI_MIND_LLM_ORCHESTRATOR_AGENT"] = "false"
os.environ["OPTI_MIND_LLM_PROVIDER"] = "openai"
os.environ["OPTI_MIND_LLM_API_KEY"] = ""

# Prefer the open-source HiGHS backend in tests unless the test explicitly
# overrides the backend, so the suite passes in environments without CPLEX.
os.environ.setdefault("OPTI_MIND_SOLVER_BACKEND", "highs")

from opti_mind.core.llm_client import LLMResponse


class FakeLLMClient:
    """Fake LLM client for testing.

    Returns a fixed string for every ``chat()`` call. If ``content`` is a
    callable, it is invoked with the messages and kwargs.
    """

    def __init__(self, content: str | Callable[..., str]) -> None:
        self.content = content

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        content = self.content(messages, **kwargs) if callable(self.content) else self.content
        return LLMResponse(content=content, model="fake")


@pytest.fixture
def fake_llm_client() -> Callable[[str], FakeLLMClient]:
    """Factory fixture for a FakeLLMClient."""

    def _make(content: str) -> FakeLLMClient:
        return FakeLLMClient(content)

    return _make

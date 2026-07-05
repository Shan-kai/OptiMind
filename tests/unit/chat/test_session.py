"""Tests for AgentSession routing and state management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from opti_mind.chat.models import ChatActionResult, ChatMessage
from opti_mind.chat.session import AgentSession
from opti_mind.config import Settings


@pytest.fixture
def orchestrator_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings with orchestrator enabled."""
    settings = Settings(llm_orchestrator_agent=True)
    monkeypatch.setattr("opti_mind.chat.session.get_settings", lambda: settings)
    return settings


@dataclass
class _FakeStateSnapshot:
    values: dict[str, Any] = field(default_factory=dict)


class _FakeGraph:
    """In-memory graph for testing AgentSession routing without LangGraph."""

    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}

    def get_state(self, config: dict[str, Any]) -> _FakeStateSnapshot | None:
        key = config["configurable"]["thread_id"]
        state = self._states.get(key)
        if state is None:
            return None
        return _FakeStateSnapshot(values=dict(state))

    def update_state(
        self,
        config: dict[str, Any],
        updates: dict[str, Any],
    ) -> None:
        key = config["configurable"]["thread_id"]
        state = self._states.setdefault(key, {})
        for k, v in updates.items():
            if k == "chat_history" and isinstance(v, list):
                state[k] = list(v)
            else:
                state[k] = v

    def stream(
        self,
        input_state: dict[str, Any] | None,
        config: dict[str, Any],
    ) -> Any:
        key = config["configurable"]["thread_id"]
        state = self._states.setdefault(key, {})
        if input_state is not None:
            # The real graph accepts LangGraph Command objects; the fake graph
            # only needs to merge plain dict updates.
            if isinstance(input_state, dict):
                state.update(input_state)
            elif hasattr(input_state, "update") and input_state.update:
                state.update(input_state.update)
        if False:
            yield {}


class FakeOrchestrator:
    """Stub orchestrator that drives routing tests."""

    def __init__(self, results: list[ChatActionResult] | None = None) -> None:
        self.calls: list[tuple[dict[str, Any], list[ChatMessage], str]] = []
        self.results = results or []
        self.index = 0

    def run(
        self,
        state: dict[str, Any],
        chat_history: list[ChatMessage],
        user_message: str,
    ) -> ChatActionResult:
        self.calls.append((state, chat_history, user_message))
        result = self.results[self.index]
        self.index += 1
        return result


def test_create_routes_to_orchestrator(orchestrator_settings: Settings) -> None:
    """Session startup is routed through the orchestrator."""
    _ = orchestrator_settings
    session_id = "test-session-create"
    graph = _FakeGraph()
    config = {"configurable": {"thread_id": session_id}}

    result = ChatActionResult(
        final_message="已识别字段映射，请确认。",
        state_updates={"field_mapping_proposal": {"fields": []}},
    )
    fake = FakeOrchestrator(results=[result])
    session = AgentSession(
        session_id=session_id,
        graph=graph,
        config=config,
        orchestrator=fake,
    )

    state = session.create({"source": "dummy.csv", "session_id": session_id, "chat_history": []})

    assert len(fake.calls) == 1
    assert fake.calls[0][2] == ""
    assert state.get("field_mapping_proposal") is not None


def test_chat_routes_to_orchestrator(orchestrator_settings: Settings) -> None:
    """User messages are routed through the orchestrator."""
    _ = orchestrator_settings
    session_id = "test-session-chat"
    graph = _FakeGraph()
    config = {"configurable": {"thread_id": session_id}}

    fake = FakeOrchestrator(
        results=[
            ChatActionResult(
                final_message="请提供映射或参数。",
                state_updates={"missing_parameters": ["c_ij"]},
            ),
            ChatActionResult(
                final_message="已收到 c_ij。",
                state_updates={
                    "instance": {
                        "problem_type": "facility_location",
                        "sets": {"I": ["c1"], "J": ["f1"]},
                        "parameters": {"c_ij": {"c1": {"f1": 1.0}}},
                    },
                    "missing_parameters": [],
                    "last_provided_parameters": {"c_ij": {"c1": {"f1": 1.0}}},
                },
            ),
        ]
    )
    session = AgentSession(
        session_id=session_id,
        graph=graph,
        config=config,
        orchestrator=fake,
    )
    session.create({"source": "dummy.csv", "session_id": session_id, "chat_history": []})

    state = session.chat("c_ij 为 1")

    assert len(fake.calls) == 2
    assert fake.calls[1][2] == "c_ij 为 1"
    assert state.get("missing_parameters") == []
    assert state["chat_history"][-1]["role"] == "assistant"


def test_session_routes_to_decision_agent_when_solution_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AgentSession routes post-solution messages to the decision agent."""
    settings = Settings(
        llm_orchestrator_agent=False,
        llm_decision_analyzer_agent=True,
    )
    monkeypatch.setattr("opti_mind.chat.session.get_settings", lambda: settings)

    session_id = "test-session-decision"
    graph = _FakeGraph()
    config = {"configurable": {"thread_id": session_id}}

    class _FakeDecisionAgent:
        def __init__(self) -> None:
            self.calls: list[tuple[dict[str, Any], list[ChatMessage], str]] = []

        def run(
            self,
            state: dict[str, Any],
            chat_history: list[ChatMessage],
            user_message: str,
        ) -> ChatActionResult:
            self.calls.append((state, chat_history, user_message))
            return ChatActionResult(
                final_message="决策分析回复",
                state_updates={},
            )

    fake_decision = _FakeDecisionAgent()
    session = AgentSession(
        session_id=session_id,
        graph=graph,
        config=config,
        decision_agent=fake_decision,
    )

    session.create({"source": "dummy.csv", "session_id": session_id, "chat_history": []})

    graph.update_state(
        config,
        {
            "solution": {"objective_value": 42.0},
            "report": {"status": "optimal"},
        },
    )

    state = session.chat("结果是什么意思")

    assert len(fake_decision.calls) == 1
    assert fake_decision.calls[0][2] == "结果是什么意思"
    assert state["chat_history"][-1]["role"] == "assistant"
    assert state["chat_history"][-1]["content"] == "决策分析回复"


def test_no_llm_agent_mode_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """When orchestrator and decision agent are disabled, chat appends and returns state."""
    settings = Settings(
        llm_orchestrator_agent=False,
        llm_decision_analyzer_agent=False,
    )
    monkeypatch.setattr("opti_mind.chat.session.get_settings", lambda: settings)

    session_id = "test-session-no-agent"
    graph = _FakeGraph()
    config = {"configurable": {"thread_id": session_id}}
    session = AgentSession(session_id=session_id, graph=graph, config=config)

    session.create({"source": "dummy.csv", "session_id": session_id, "chat_history": []})
    state = session.chat("hello")

    assert state["chat_history"][-1]["role"] == "user"
    assert state["chat_history"][-1]["content"] == "hello"


def test_deterministic_parameter_extraction(orchestrator_settings: Settings) -> None:
    """User-provided parameter values are applied before the orchestrator runs."""
    _ = orchestrator_settings
    session_id = "test-session-deterministic-param"
    graph = _FakeGraph()
    config = {"configurable": {"thread_id": session_id}}

    fake = FakeOrchestrator(
        results=[
            ChatActionResult(final_message="", state_updates={}),
            ChatActionResult(final_message="收到", state_updates={}),
        ]
    )
    session = AgentSession(
        session_id=session_id,
        graph=graph,
        config=config,
        orchestrator=fake,
    )
    session.create(
        {
            "source": "dummy.csv",
            "session_id": session_id,
            "chat_history": [],
            "field_mapping_confirmed": True,
            "field_mapping_proposal": {"fields": []},
            "instance": {
                "problem_type": "inventory",
                "sets": {},
                "parameters": {},
                "meta": {"ontology_entry": {"metadata": {}}},
            },
            "missing_parameters": ["M"],
        }
    )

    state = session.chat("M=10000")

    assert len(fake.calls) == 2
    # The orchestrator must see the parameter already applied.
    orchestrator_state = fake.calls[1][0]
    assert orchestrator_state["missing_parameters"] == []
    assert orchestrator_state["instance"]["parameters"]["M"] == 10000.0
    assert orchestrator_state["last_provided_parameters"] == {"M": 10000.0}
    assert state["chat_history"][-1]["content"] == "收到"


def test_deterministic_parameter_extraction_confirms_mapping(
    orchestrator_settings: Settings,
) -> None:
    """Providing a parameter before confirming mapping also confirms the mapping."""
    _ = orchestrator_settings
    session_id = "test-session-deterministic-confirm"
    graph = _FakeGraph()
    config = {"configurable": {"thread_id": session_id}}

    fake = FakeOrchestrator(
        results=[
            ChatActionResult(final_message="", state_updates={}),
            ChatActionResult(final_message="已确认并提交", state_updates={}),
        ]
    )
    session = AgentSession(
        session_id=session_id,
        graph=graph,
        config=config,
        orchestrator=fake,
    )
    session.create(
        {
            "source": "dummy.csv",
            "session_id": session_id,
            "chat_history": [],
            "field_mapping_confirmed": False,
            "field_mapping_proposal": {"fields": []},
            "instance": {
                "problem_type": "facility_location",
                "sets": {"I": ["c1", "c2"], "J": ["f1", "f2"]},
                "parameters": {},
                "meta": {
                    "ontology_entry": {
                        "metadata": {"keyword_aliases": {"c": ["cost", "transport_cost"]}}
                    }
                },
            },
            "missing_parameters": ["c_ij"],
        }
    )

    state = session.chat("c_ij:1,2;3,4")

    assert len(fake.calls) == 2
    orchestrator_state = fake.calls[1][0]
    assert orchestrator_state["field_mapping_confirmed"] is True
    assert orchestrator_state["missing_parameters"] == []
    assert orchestrator_state["instance"]["parameters"]["c_ij"] == {
        "c1": {"f1": 1.0, "f2": 2.0},
        "c2": {"f1": 3.0, "f2": 4.0},
    }
    assert "cost" in orchestrator_state.get("confirmed_missing_roles", [])
    assert state["chat_history"][-1]["content"] == "已确认并提交"


def test_resume_data_intelligence_when_user_provides_value(
    orchestrator_settings: Settings,
) -> None:
    """A pending data_intelligence clarification is resumed when the user gives a value."""
    _ = orchestrator_settings
    session_id = "test-resume-data-intelligence"
    graph = _FakeGraph()
    config = {"configurable": {"thread_id": session_id}}
    fake = FakeOrchestrator(results=[ChatActionResult(final_message="", state_updates={})])
    session = AgentSession(
        session_id=session_id,
        graph=graph,
        config=config,
        orchestrator=fake,
    )
    session.create({"source": "dummy.csv", "session_id": session_id, "chat_history": []})
    session.graph.update_state(
        config,
        {
            "instance": {
                "problem_type": "inventory",
                "sets": {"I": ["i1"], "T": ["t1"]},
                "parameters": {},
                "meta": {},
            },
            "pending_clarification": {
                "station": "data_intelligence",
                "expected_field": "M",
                "question": "Need M",
                "options": [],
                "context": {},
            },
            "missing_parameters": [],
        },
    )

    resumed = session._maybe_resume_data_intelligence(session.get_state(), "M=10000")

    assert resumed is True
    assert session.get_state()["instance"]["parameters"]["M"] == 10000.0


def test_apply_agent_result_preserves_empty_missing_when_awaiting_input(
    orchestrator_settings: Settings,
) -> None:
    """If the pipeline is awaiting input, do not re-add cleared missing parameters."""
    _ = orchestrator_settings
    session_id = "test-no-clobber-missing"
    graph = _FakeGraph()
    config = {"configurable": {"thread_id": session_id}}
    fake = FakeOrchestrator(results=[ChatActionResult(final_message="", state_updates={})])
    session = AgentSession(
        session_id=session_id,
        graph=graph,
        config=config,
        orchestrator=fake,
    )
    session.create({"source": "dummy.csv", "session_id": session_id, "chat_history": []})
    session.graph.update_state(
        config,
        {
            "field_mapping_confirmed": True,
            "missing_parameters": [],
            "pending_clarification": None,
        },
    )

    result = ChatActionResult(
        final_message="Need c_ij",
        state_updates={
            "missing_parameters": ["c_ij"],
            "pending_clarification": {
                "station": "modeling",
                "expected_field": "c_ij",
                "question": "What is c_ij?",
                "options": [],
                "context": {},
            },
        },
    )
    session._apply_agent_result(result)
    state = session.get_state()

    assert state["missing_parameters"] == []
    assert state["pending_clarification"] is not None

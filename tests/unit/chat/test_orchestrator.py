"""Tests for the LLM-driven optimization orchestrator."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from opti_mind.chat.models import ChatActionResult, ChatMessage
from opti_mind.chat.orchestrator import OptimizationOrchestrator
from opti_mind.chat.orchestrator_tools import (
    OrchestratorToolExecutor,
    execute_orchestrator_tool_call,
)
from opti_mind.chat.session import AgentSession
from opti_mind.config import Settings
from opti_mind.core.llm_client import LLMResponse
from opti_mind.data.models import ColumnProfile, DataProfileReport, OptimizationInstance
from opti_mind.ontology.models import OntologyEntry, ProblemType
from opti_mind.ontology.service import ParameterInfo, ProblemTypeDetail
from opti_mind.workflow.clarification import ClarificationRequest


class FakeLLMClientQueue:
    """Fake LLM client that returns a queued sequence of JSON responses."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.index = 0
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        self.calls.append(messages)
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


class FakeDataService:
    """Stub DataService returning a deterministic DataFrame and instance."""

    def __init__(self) -> None:
        self.schema_interpreter = MagicMock()

    def load_df(self, source: str) -> pd.DataFrame:
        del source
        return pd.DataFrame(
            {
                "customer": ["c1", "c2"],
                "demand": [10.0, 20.0],
                "facility": ["f1", "f2"],
                "capacity": [100.0, 200.0],
                "fixed_cost": [5.0, 6.0],
            }
        )

    @property
    def profiler(self) -> Any:
        prof = MagicMock()
        prof.profile.return_value = DataProfileReport(
            n_rows=2,
            n_cols=5,
            columns=[
                ColumnProfile(
                    name="customer",
                    dtype="object",
                    missing_rate=0.0,
                    non_null_count=2,
                    unique_count=2,
                    cardinality=1.0,
                ),
                ColumnProfile(
                    name="demand",
                    dtype="float64",
                    missing_rate=0.0,
                    non_null_count=2,
                    unique_count=2,
                    cardinality=1.0,
                ),
                ColumnProfile(
                    name="facility",
                    dtype="object",
                    missing_rate=0.0,
                    non_null_count=2,
                    unique_count=2,
                    cardinality=1.0,
                ),
                ColumnProfile(
                    name="capacity",
                    dtype="float64",
                    missing_rate=0.0,
                    non_null_count=2,
                    unique_count=2,
                    cardinality=1.0,
                ),
                ColumnProfile(
                    name="fixed_cost",
                    dtype="float64",
                    missing_rate=0.0,
                    non_null_count=2,
                    unique_count=2,
                    cardinality=1.0,
                ),
            ],
        )
        return prof

    def rebuild_instance(
        self,
        df: pd.DataFrame,
        semantics: list[Any],
        dataset_id: str = "",
        problem_type: str | None = None,
    ) -> OptimizationInstance:
        del df, semantics, dataset_id
        if problem_type == "inventory":
            return OptimizationInstance(
                problem_type="inventory",
                sets={"I": ["i1"], "T": ["t1", "t2"]},
                parameters={
                    "d": {"i1": {"t1": 5.0, "t2": 7.0}},
                    "h": {"i1": 1.0},
                    "s": {"i1": 10.0},
                    "c": {"i1": 2.0},
                    "I0": {"i1": 0.0},
                    "M": 12.0,
                },
                meta={},
            )
        return OptimizationInstance(
            problem_type=problem_type or "facility_location",
            sets={"I": ["c1", "c2"], "J": ["f1", "f2"]},
            parameters={"d_i": {"c1": 10.0, "c2": 20.0}, "Q_j": {"f1": 100.0, "f2": 200.0}},
            meta={},
        )


class FakeOntologyService:
    """Stub ontology service exposing required parameters for facility location."""

    def get_detail(self, problem_type: str) -> ProblemTypeDetail | None:
        del problem_type
        return ProblemTypeDetail(
            value="facility_location",
            label="Facility Location",
            parameters=[
                ParameterInfo(symbol="d_i", base_name="d", description="demand", shape="vector"),
                ParameterInfo(symbol="Q_j", base_name="Q", description="capacity", shape="vector"),
                ParameterInfo(
                    symbol="f_j", base_name="f", description="fixed cost", shape="vector"
                ),
                ParameterInfo(
                    symbol="c_ij", base_name="c", description="transport cost", shape="matrix"
                ),
            ],
        )

    def get_entry(self, problem_type: str) -> OntologyEntry | None:
        if problem_type == "inventory":
            return OntologyEntry(
                problem_type=ProblemType.INVENTORY,
                description="Inventory problem",
                sets={"I": "items", "T": "periods"},
                parameters={
                    "d_it": "demand",
                    "h_i": "holding cost",
                    "s_i": "ordering cost",
                    "c_i": "purchase cost",
                    "I0_i": "initial inventory",
                    "M": "big-M",
                },
                signature={
                    "required_parameters": ["d_it", "h_i", "s_i", "c_i"],
                    "auto_computed_parameters": ["M"],
                },
                aliases={"d": ["d_it"], "h": ["h_i"], "s": ["s_i"], "c": ["c_i"], "I0": ["I0_i"]},
                metadata={
                    "keyword_aliases": {
                        "d": ["demand"],
                        "h": ["holding_cost"],
                        "s": ["ordering_cost", "setup_cost"],
                        "c": ["purchase_cost", "unit_cost"],
                        "I0": ["initial_inventory"],
                    }
                },
            )
        return OntologyEntry(
            problem_type=ProblemType.FACILITY_LOCATION,
            description="Facility location problem",
            sets={"I": "customers", "J": "facilities"},
            parameters={
                "d_i": "demand",
                "Q_j": "capacity",
                "f_j": "fixed cost",
                "c_ij": "transport cost",
            },
            signature={"required_parameters": ["d_i", "Q_j", "f_j", "c_ij"]},
            aliases={"f": ["fixed_cost"], "c": ["cost", "transport_cost"]},
            metadata={
                "keyword_aliases": {
                    "d": ["demand"],
                    "Q": ["capacity"],
                    "f": ["fixed_cost"],
                    "c": ["cost", "transport_cost", "shipping_cost"],
                }
            },
        )


def test_analyze_data_returns_proposal_and_missing_parameters() -> None:
    """analyze_data builds an instance and reports missing parameters."""
    executor = OrchestratorToolExecutor(
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )
    state: dict[str, Any] = {"source": "dummy.csv"}

    result = executor.execute({"tool": "analyze_data", "input": {}}, state)

    assert result["status"] == "ok"
    assert "proposal" in result["result"]
    assert "c_ij" in result["result"]["missing_parameters"]
    assert set(result["state_updates"]["missing_parameters"]) == {"f_j", "c_ij"}
    assert result["state_updates"]["field_mapping_proposal"] is not None


def test_analyze_data_inventory_does_not_ask_for_auto_computed_m() -> None:
    """analyze_data must not list the auto-computed big-M as missing."""
    executor = OrchestratorToolExecutor(
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )
    state: dict[str, Any] = {"source": "dummy.csv", "problem_type": "inventory"}

    result = executor.execute({"tool": "analyze_data", "input": {}}, state)

    assert result["status"] == "ok"
    assert "M" not in result["result"]["missing_parameters"]
    assert result["result"]["missing_parameters"] == []


def test_analyze_data_preserves_manually_provided_parameters() -> None:
    """Re-running analyze_data must not drop parameters the user already submitted."""
    executor = OrchestratorToolExecutor(
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )
    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1", "c2"], "J": ["f1", "f2"]},
        parameters={"c_ij": {"c1": {"f1": 1.0, "f2": 2.0}, "c2": {"f1": 3.0, "f2": 4.0}}},
    )
    state: dict[str, Any] = {
        "source": "dummy.csv",
        "instance": instance.model_dump(mode="json"),
        "last_provided_parameters": {"c_ij": instance.parameters["c_ij"]},
        "field_mapping_confirmed": True,
    }

    result = executor.execute({"tool": "analyze_data", "input": {}}, state)

    assert result["status"] == "ok"
    assert "c_ij" not in result["state_updates"]["missing_parameters"]
    assert result["state_updates"]["instance"]["parameters"]["c_ij"] == {
        "c1": {"f1": 1.0, "f2": 2.0},
        "c2": {"f1": 3.0, "f2": 4.0},
    }


def test_confirm_mapping_updates_state() -> None:
    """confirm_mapping marks the mapping proposal as confirmed."""
    executor = OrchestratorToolExecutor(
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )
    state: dict[str, Any] = {"field_mapping_proposal": {"fields": []}}

    result = executor.execute({"tool": "confirm_mapping", "input": {}}, state)

    assert result["status"] == "ok"
    assert result["state_updates"]["field_mapping_confirmed"] is True


def test_submit_parameters_applies_values_and_updates_missing_list() -> None:
    """submit_parameters patches the instance and drops provided symbols from missing."""
    executor = OrchestratorToolExecutor(
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )
    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1", "c2"], "J": ["f1", "f2"]},
        parameters={},
    )
    state: dict[str, Any] = {
        "instance": instance.model_dump(mode="json"),
        "missing_parameters": ["f_j", "c_ij"],
    }

    result = executor.execute(
        {"tool": "submit_parameters", "input": {"parameters": {"f_j": [5.0, 6.0]}}},
        state,
    )

    assert result["status"] == "ok"
    assert result["result"]["provided"] == ["f_j"]
    assert result["state_updates"]["missing_parameters"] == ["c_ij"]
    assert result["state_updates"]["instance"]["parameters"]["f_j"] == {
        "f1": 5.0,
        "f2": 6.0,
    }


def test_get_status_returns_snapshot() -> None:
    """get_status reports mapping confirmation, missing params, and pipeline stages."""
    executor = OrchestratorToolExecutor(
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )
    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"J": ["f1"]},
        parameters={"f_j": {"f1": 1.0}},
    )
    state: dict[str, Any] = {
        "field_mapping_confirmed": True,
        "missing_parameters": ["c_ij"],
        "instance": instance.model_dump(mode="json"),
    }

    result = executor.execute({"tool": "get_status", "input": {}}, state)

    assert result["status"] == "ok"
    assert result["result"]["field_mapping_confirmed"] is True
    assert result["result"]["missing_parameters"] == ["c_ij"]
    assert result["result"]["pipeline_stages"] == ["data_intelligence"]


def test_execute_orchestrator_tool_call_wrapper() -> None:
    """The convenience wrapper dispatches to the executor."""
    result = execute_orchestrator_tool_call(
        {"tool": "confirm_mapping", "input": {}},
        {"field_mapping_proposal": {"fields": []}},
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )
    assert result["status"] == "ok"


def test_orchestrator_ask_user_after_analyze_data() -> None:
    """The orchestrator can analyze data and then ask the user for missing params."""
    responses = [
        _response(
            final_message="",
            tool_calls=[{"tool": "analyze_data", "input": {}}],
        ),
        _response(
            final_message="unused because ask_user overrides",
            tool_calls=[{"tool": "ask_user", "input": {"question": "c_ij?"}}],
        ),
    ]
    fake_llm = FakeLLMClientQueue(responses)
    orchestrator = OptimizationOrchestrator(
        llm_client=fake_llm,
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )

    result = orchestrator.run(
        state={"source": "dummy.csv"},
        chat_history=[],
        user_message="",
    )

    # ask_user tool result overrides final_message with its question.
    assert result.final_message == "c_ij?"
    assert set(result.state_updates.get("missing_parameters", [])) == {"f_j", "c_ij"}
    assert result.state_updates.get("field_mapping_proposal") is not None


def _fake_graph_factory(state_updates: dict[str, Any] | None = None) -> Any:
    """Return a fake graph class that yields a single event and exposes final state."""

    class _FakeGraph:
        def __init__(self) -> None:
            self._states: dict[str, dict[str, Any]] = {}

        def get_state(self, config: dict[str, Any]) -> Any:
            key = config["configurable"]["thread_id"]
            return MagicMock(values=self._states.setdefault(key, {}))

        def stream(
            self,
            input_state: dict[str, Any] | None,
            config: dict[str, Any],
        ) -> Any:
            key = config["configurable"]["thread_id"]
            state = self._states.setdefault(key, {})
            if input_state is not None:
                state.update(input_state)
            if state_updates:
                state.update(state_updates)
            if False:
                yield {}

    return _FakeGraph


def test_orchestrator_submit_parameters_then_run_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The orchestrator can submit values and run the pipeline to success."""
    monkeypatch.setattr(
        "opti_mind.chat.orchestrator_tools.build_optimization_graph",
        _fake_graph_factory({"report": {"objective": 42.0}, "solution": {"x": 1.0}}),
    )

    responses = [
        _response(
            final_message="",
            tool_calls=[
                {"tool": "submit_parameters", "input": {"parameters": {"f_j": [5.0, 6.0]}}}
            ],
        ),
        _response(
            final_message="",
            tool_calls=[{"tool": "run_pipeline", "input": {}}],
        ),
        _response(
            final_message="pipeline succeeded",
            tool_calls=[],
        ),
    ]
    fake_llm = FakeLLMClientQueue(responses)
    orchestrator = OptimizationOrchestrator(
        llm_client=fake_llm,
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )

    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1", "c2"], "J": ["f1", "f2"]},
        parameters={},
    )
    state: dict[str, Any] = {
        "source": "dummy.csv",
        "session_id": "s1",
        "instance": instance.model_dump(mode="json"),
        "missing_parameters": ["f_j"],
        "field_mapping_confirmed": True,
    }

    result = orchestrator.run(state=state, chat_history=[], user_message="f_j=5,6")

    assert result.final_message == "pipeline succeeded"
    assert result.state_updates.get("instance", {}).get("parameters", {}).get("f_j") == {
        "f1": 5.0,
        "f2": 6.0,
    }
    assert result.state_updates.get("missing_parameters") == []
    assert result.state_updates.get("report") == {"objective": 42.0}


def test_orchestrator_run_pipeline_reports_awaiting_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If run_pipeline interrupts, the orchestrator surfaces the question."""

    class _InterruptingGraph:
        def __init__(self) -> None:
            self._states: dict[str, dict[str, Any]] = {}

        def get_state(self, config: dict[str, Any]) -> Any:
            key = config["configurable"]["thread_id"]
            return MagicMock(values=self._states.setdefault(key, {}))

        def stream(
            self,
            input_state: dict[str, Any] | None,
            config: dict[str, Any],
        ) -> Any:
            key = config["configurable"]["thread_id"]
            state = self._states.setdefault(key, {})
            if input_state is not None:
                state.update(input_state)
            req = ClarificationRequest(
                station="modeling",
                expected_field="c_ij",
                question="What is c_ij?",
                options=[],
                context={},
            )
            state["pending_clarification"] = req.model_dump()
            yield {"__interrupt__": [_FakeInterruptValue(req)]}

    class _FakeInterruptValue:
        def __init__(self, value: ClarificationRequest) -> None:
            self.value = value

    monkeypatch.setattr(
        "opti_mind.chat.orchestrator_tools.build_optimization_graph",
        _InterruptingGraph,
    )

    responses = [
        _response(
            final_message="",
            tool_calls=[{"tool": "run_pipeline", "input": {}}],
        ),
    ]
    fake_llm = FakeLLMClientQueue(responses)
    orchestrator = OptimizationOrchestrator(
        llm_client=fake_llm,
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )

    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1", "c2"], "J": ["f1", "f2"]},
        parameters={"f_j": {"f1": 5.0, "f2": 6.0}},
    )
    state: dict[str, Any] = {
        "source": "dummy.csv",
        "session_id": "s1",
        "instance": instance.model_dump(mode="json"),
        "missing_parameters": [],
        "field_mapping_confirmed": True,
    }

    result = orchestrator.run(state=state, chat_history=[], user_message="run")

    assert "c_ij" in result.final_message
    assert result.state_updates.get("pending_clarification") is not None


def test_submit_parameters_then_run_pipeline_preserves_c_ij(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: manually provided c_ij must be synced to the pipeline checkpoint.

    Before the fix, _run_pipeline streamed from the stale LangGraph checkpoint,
    so the pipeline would ask for c_ij again even though the orchestrator had
    just applied it via submit_parameters.
    """

    class _FakeInterruptValue:
        def __init__(self, value: ClarificationRequest) -> None:
            self.value = value

    class _CheckpointingGraph:
        def __init__(self) -> None:
            self._states: dict[str, dict[str, Any]] = {}
            self.update_state_calls: list[dict[str, Any]] = []

        def get_state(self, config: dict[str, Any]) -> Any:
            key = config["configurable"]["thread_id"]
            return MagicMock(values=self._states.setdefault(key, {}))

        def update_state(
            self,
            config: dict[str, Any],
            updates: dict[str, Any],
        ) -> None:
            key = config["configurable"]["thread_id"]
            self.update_state_calls.append(dict(updates))
            state = self._states.setdefault(key, {})
            state.update(updates)

        def stream(
            self,
            input_state: dict[str, Any] | None,
            config: dict[str, Any],
        ) -> Any:
            del input_state
            key = config["configurable"]["thread_id"]
            state = self._states.setdefault(key, {})
            instance = state.get("instance", {})
            params = instance.get("parameters", {})
            if "c_ij" not in params:
                req = ClarificationRequest(
                    station="modeling",
                    expected_field="c_ij",
                    question="What is c_ij?",
                    options=[],
                    context={},
                )
                state["pending_clarification"] = req.model_dump()
                yield {"__interrupt__": [_FakeInterruptValue(req)]}
                return
            state["report"] = {"objective": 42.0}
            state["solution"] = {"x": 1.0}
            state["missing_parameters"] = []
            if False:
                yield {}

    monkeypatch.setattr(
        "opti_mind.chat.orchestrator_tools.build_optimization_graph",
        _CheckpointingGraph,
    )

    responses = [
        _response(
            final_message="",
            tool_calls=[
                {
                    "tool": "submit_parameters",
                    "input": {
                        "parameters": {"c_ij": [1.0, 2.0, 5.0, 4.0, 2.0, 5.0, 3.0, 2.0, 4.0]}
                    },
                }
            ],
        ),
        _response(
            final_message="",
            tool_calls=[{"tool": "run_pipeline", "input": {}}],
        ),
        _response(
            final_message="pipeline succeeded with your c_ij",
            tool_calls=[],
        ),
    ]
    fake_llm = FakeLLMClientQueue(responses)
    orchestrator = OptimizationOrchestrator(
        llm_client=fake_llm,
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )

    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1", "c2", "c3"], "J": ["f1", "f2", "f3"]},
        parameters={"f_j": {"f1": 5.0, "f2": 6.0, "f3": 8.0}},
    )
    state: dict[str, Any] = {
        "source": "dummy.csv",
        "session_id": "s1",
        "instance": instance.model_dump(mode="json"),
        "missing_parameters": ["c_ij"],
        "field_mapping_confirmed": True,
    }

    result = orchestrator.run(
        state=state,
        chat_history=[],
        user_message="c_ij:1,2,5;4,2,5;3,2,4",
    )

    assert result.final_message == "pipeline succeeded with your c_ij"
    assert result.state_updates.get("report") == {"objective": 42.0}
    assert result.state_updates.get("missing_parameters") == []
    assert result.state_updates.get("instance", {}).get("parameters", {}).get("c_ij") == {
        "c1": {"f1": 1.0, "f2": 2.0, "f3": 5.0},
        "c2": {"f1": 4.0, "f2": 2.0, "f3": 5.0},
        "c3": {"f1": 3.0, "f2": 2.0, "f3": 4.0},
    }


def test_submit_parameters_records_last_provided_parameters() -> None:
    """submit_parameters stores the successfully applied value for later reuse."""
    executor = OrchestratorToolExecutor(
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )
    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1", "c2"], "J": ["f1", "f2"]},
        parameters={"f_j": {"f1": 5.0, "f2": 6.0}},
    )
    state: dict[str, Any] = {
        "instance": instance.model_dump(mode="json"),
        "missing_parameters": ["c_ij"],
        "field_mapping_confirmed": True,
    }

    result = executor.execute(
        {"tool": "submit_parameters", "input": {"parameters": {"c_ij": [1.0, 2.0, 3.0, 4.0]}}},
        state,
    )

    assert result["status"] == "ok"
    assert result["state_updates"]["last_provided_parameters"]["c_ij"] == {
        "c1": {"f1": 1.0, "f2": 2.0},
        "c2": {"f1": 3.0, "f2": 4.0},
    }


def test_submit_parameters_marks_role_as_confirmed_missing() -> None:
    """Providing a parameter value directly implies the CSV column is absent."""
    executor = OrchestratorToolExecutor(
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )
    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1", "c2"], "J": ["f1", "f2"]},
        parameters={"f_j": {"f1": 5.0, "f2": 6.0}},
        meta={"ontology_entry": FakeOntologyService().get_entry("facility_location")},
    )
    state: dict[str, Any] = {
        "instance": instance.model_dump(mode="json"),
        "missing_parameters": ["c_ij"],
        "field_mapping_confirmed": True,
    }

    result = executor.execute(
        {"tool": "submit_parameters", "input": {"parameters": {"c_ij": [1.0, 2.0, 3.0, 4.0]}}},
        state,
    )

    assert result["status"] == "ok"
    assert "cost" in result["state_updates"].get("confirmed_missing_roles", [])


def test_get_status_exposes_last_provided_parameters() -> None:
    """get_status returns last_provided_parameters so the LLM can reuse values."""
    executor = OrchestratorToolExecutor(
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )
    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"J": ["f1"]},
        parameters={"f_j": {"f1": 1.0}},
    )
    state: dict[str, Any] = {
        "instance": instance.model_dump(mode="json"),
        "last_provided_parameters": {"f_j": {"f1": 5.0}},
    }

    result = executor.execute({"tool": "get_status", "input": {}}, state)

    assert result["status"] == "ok"
    assert result["result"]["last_provided_parameters"] == {"f_j": {"f1": 5.0}}


def test_orchestrator_reuses_last_provided_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the user confirms reusing a previous value, the orchestrator submits it again."""

    class _CheckpointingGraph:
        def __init__(self) -> None:
            self._states: dict[str, dict[str, Any]] = {}

        def get_state(self, config: dict[str, Any]) -> Any:
            key = config["configurable"]["thread_id"]
            return MagicMock(values=self._states.setdefault(key, {}))

        def update_state(
            self,
            config: dict[str, Any],
            updates: dict[str, Any],
        ) -> None:
            key = config["configurable"]["thread_id"]
            state = self._states.setdefault(key, {})
            state.update(updates)

        def stream(
            self,
            input_state: dict[str, Any] | None,
            config: dict[str, Any],
        ) -> Any:
            del input_state
            key = config["configurable"]["thread_id"]
            state = self._states.setdefault(key, {})
            if "c_ij" in state.get("instance", {}).get("parameters", {}):
                state["report"] = {"objective": 42.0}
                state["solution"] = {"x": 1.0}
                state["missing_parameters"] = []
            if False:
                yield {}

    monkeypatch.setattr(
        "opti_mind.chat.orchestrator_tools.build_optimization_graph",
        _CheckpointingGraph,
    )

    responses = [
        _response(
            final_message="",
            tool_calls=[
                {
                    "tool": "get_status",
                    "input": {},
                }
            ],
        ),
        _response(
            final_message="",
            tool_calls=[
                {
                    "tool": "submit_parameters",
                    "input": {
                        "parameters": {"c_ij": [1.0, 2.0, 5.0, 4.0, 2.0, 5.0, 3.0, 2.0, 4.0]}
                    },
                }
            ],
        ),
        _response(
            final_message="",
            tool_calls=[{"tool": "run_pipeline", "input": {}}],
        ),
        _response(
            final_message="沿用上次的 c_ij，求解完成。",
            tool_calls=[],
        ),
    ]
    fake_llm = FakeLLMClientQueue(responses)
    orchestrator = OptimizationOrchestrator(
        llm_client=fake_llm,
        ontology_service=FakeOntologyService(),
        data_service=FakeDataService(),
    )

    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1", "c2", "c3"], "J": ["f1", "f2", "f3"]},
        parameters={"f_j": {"f1": 5.0, "f2": 6.0, "f3": 8.0}},
    )
    state: dict[str, Any] = {
        "source": "dummy.csv",
        "session_id": "s1",
        "instance": instance.model_dump(mode="json"),
        "missing_parameters": ["c_ij"],
        "field_mapping_confirmed": True,
        "last_provided_parameters": {
            "c_ij": {
                "c1": {"f1": 1.0, "f2": 2.0, "f3": 5.0},
                "c2": {"f1": 4.0, "f2": 2.0, "f3": 5.0},
                "c3": {"f1": 3.0, "f2": 2.0, "f3": 4.0},
            }
        },
    }

    result = orchestrator.run(
        state=state,
        chat_history=[],
        user_message="确认，用之前的矩阵",
    )

    assert result.final_message == "沿用上次的 c_ij，求解完成。"
    assert result.state_updates.get("report") == {"objective": 42.0}


def test_session_uses_orchestrator_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """AgentSession routes through the orchestrator when llm_orchestrator_agent is on."""
    settings = Settings(llm_orchestrator_agent=True)
    monkeypatch.setattr("opti_mind.chat.session.get_settings", lambda: settings)

    class _FakeGraph:
        def __init__(self) -> None:
            self._states: dict[str, dict[str, Any]] = {}

        def get_state(self, config: dict[str, Any]) -> Any:
            key = config["configurable"]["thread_id"]
            return MagicMock(values=self._states.setdefault(key, {}))

        def update_state(self, config: dict[str, Any], updates: dict[str, Any]) -> None:
            key = config["configurable"]["thread_id"]
            state = self._states.setdefault(key, {})
            state.update(updates)

        def stream(
            self,
            input_state: dict[str, Any] | None,
            config: dict[str, Any],
        ) -> Any:
            key = config["configurable"]["thread_id"]
            state = self._states.setdefault(key, {})
            if input_state is not None:
                state.update(input_state)
            if False:
                yield {}

    class _FakeOrchestrator:
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
                final_message="orchestrator reply",
                state_updates={"orchestrator_applied": True},
            )

    session_id = "test-session-orchestrator"
    graph = _FakeGraph()
    config = {"configurable": {"thread_id": session_id}}
    fake_orchestrator = _FakeOrchestrator()
    session = AgentSession(
        session_id=session_id,
        graph=graph,
        config=config,
        orchestrator=fake_orchestrator,
    )

    session.create({"source": "dummy.csv", "session_id": session_id, "chat_history": []})
    assert len(fake_orchestrator.calls) == 1
    assert session.get_state()["orchestrator_applied"] is True

    session.chat("confirm")
    assert len(fake_orchestrator.calls) == 2
    assert fake_orchestrator.calls[1][2] == "confirm"

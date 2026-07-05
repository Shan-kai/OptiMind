"""End-to-end regression tests using scale-8 fixtures.

Each fixture represents a problem with roughly eight entities and a known or
stable optimal solution. The tests exercise the full deterministic pipeline
(LLM switches forced off) and verify that the solver reaches an optimal state.
"""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from opti_mind.config import Settings
from opti_mind.data.schema import HeuristicSchemaInterpreter
from opti_mind.data.service import DataService
from opti_mind.modeling.generator import IRGenerator
from opti_mind.solver.router import SolverRouter
from opti_mind.workflow import engine as engine_mod
from opti_mind.workflow.context import WorkflowDependencies, default_workflow_dependencies
from opti_mind.workflow.engine import build_optimization_graph

FACILITY_LOCATION = "tests/fixtures/facility_location.csv"
ASSIGNMENT = "tests/fixtures/assignment.csv"
TRANSPORTATION = "tests/fixtures/transportation.csv"
KNAPSACK = "tests/fixtures/knapsack.csv"
SCHEDULING = "tests/fixtures/scheduling.csv"
INVENTORY = "tests/fixtures/inventory.csv"
NETWORK_FLOW = "tests/fixtures/network_flow.csv"


def _run(monkeypatch, source: str, problem_type: str, thread_id: str) -> dict:
    monkeypatch.setattr(
        engine_mod,
        "get_settings",
        lambda: Settings(llm_schema_interpreter=False, llm_model_generator=False),
    )

    # Force the heuristic schema interpreter and deterministic IR generator so
    # golden tests are stable even when the local .env enables LLM layers.
    data_service = DataService(schema_interpreter=HeuristicSchemaInterpreter())
    ir_generator = IRGenerator(use_llm=False)
    base_deps = default_workflow_dependencies()
    mock_solver_router = SolverRouter()
    mock_solver_router._settings = Settings(solver_backend="highs")
    custom_deps = WorkflowDependencies(
        data_service=data_service,
        ontology_service=base_deps.ontology_service,
        ir_generator=ir_generator,
        model_validator=base_deps.model_validator,
        solver_router=mock_solver_router,
        decision_service=base_deps.decision_service,
        memory_saver=MemorySaver(),
    )
    monkeypatch.setattr(
        engine_mod,
        "default_workflow_dependencies",
        lambda: custom_deps,
    )

    graph = build_optimization_graph()
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(
        {"errors": [], "source": source, "problem_type": problem_type},
        config=config,
    )
    return result


def test_facility_location(monkeypatch) -> None:
    result = _run(monkeypatch, FACILITY_LOCATION, "facility_location", "fl-scale8")
    assert result.get("errors") == []
    solution = result.get("solution")
    assert solution is not None
    assert solution["status"] == "optimal"
    assert isinstance(solution["objective_value"], (int, float))

    variables = solution.get("variables", {})
    y_j = variables.get("y_j", {})
    x_ij = variables.get("x_ij", {})
    assert any(v == 1.0 for v in y_j.values()), f"expected an open facility, got y_j={y_j}"
    assert any(v == 1.0 for v in x_ij.values()), f"expected an assignment, got x_ij={x_ij}"


def test_assignment(monkeypatch) -> None:
    result = _run(monkeypatch, ASSIGNMENT, "assignment", "assign-scale8")
    assert result.get("errors") == []
    solution = result.get("solution")
    assert solution is not None
    assert solution["status"] == "optimal"
    assert solution["objective_value"] == 40.0

    variables = solution.get("variables", {})
    x_ij = variables.get("x_ij", {})
    for i in range(1, 9):
        assert x_ij.get(f"a{i}_t{i}") == 1.0, f"expected a{i}->t{i}, got x_ij={x_ij}"


def test_transportation(monkeypatch) -> None:
    result = _run(monkeypatch, TRANSPORTATION, "transportation", "trans-scale8")
    assert result.get("errors") == []
    solution = result.get("solution")
    assert solution is not None
    assert solution["status"] == "optimal"
    assert isinstance(solution["objective_value"], (int, float))


def test_knapsack(monkeypatch) -> None:
    result = _run(monkeypatch, KNAPSACK, "knapsack", "kp-scale8")
    assert result.get("errors") == []
    solution = result.get("solution")
    assert solution is not None
    assert solution["status"] == "optimal"
    assert solution["objective_value"] == 84.0

    variables = solution.get("variables", {})
    x_i = variables.get("x_i", {})
    for item in ["i1", "i2", "i3", "i4", "i5", "i6", "i7"]:
        assert x_i.get(item) == 1.0, f"expected {item} selected, got x_i={x_i}"
    assert x_i.get("i8") == 0.0, f"expected i8 not selected, got x_i={x_i}"


def test_scheduling(monkeypatch) -> None:
    result = _run(monkeypatch, SCHEDULING, "scheduling", "sched-scale8")
    assert result.get("errors") == []
    solution = result.get("solution")
    assert solution is not None
    assert solution["status"] == "optimal"
    assert solution["objective_value"] == pytest.approx(137.0, abs=1e-3)

    variables = solution.get("variables", {})
    c_j = variables.get("C_j", {})
    assert len(c_j) == 8, f"expected completion times for 8 jobs, got c_j={c_j}"


def test_inventory(monkeypatch) -> None:
    result = _run(monkeypatch, INVENTORY, "inventory", "inv-scale8")
    assert result.get("errors") == []
    solution = result.get("solution")
    assert solution is not None
    assert solution["status"] == "optimal"
    assert isinstance(solution["objective_value"], (int, float))

    variables = solution.get("variables", {})
    x_it = variables.get("x_it", {})
    y_it = variables.get("y_it", {})
    assert any(v > 0 for v in x_it.values()), f"expected orders, got x_it={x_it}"
    assert any(v == 1.0 for v in y_it.values()), f"expected order flags, got y_it={y_it}"


def test_network_flow(monkeypatch) -> None:
    result = _run(monkeypatch, NETWORK_FLOW, "network_flow", "nf-scale8")
    assert result.get("errors") == []
    solution = result.get("solution")
    assert solution is not None
    assert solution["status"] == "optimal"
    assert solution["objective_value"] == 535.0

    variables = solution.get("variables", {})
    x_ij = variables.get("x_ij", {})
    assert x_ij.get("n1_n2") == 20.0
    assert x_ij.get("n1_n3") == 10.0
    assert x_ij.get("n5_n8") == 15.0
    assert x_ij.get("n7_n8") == 15.0

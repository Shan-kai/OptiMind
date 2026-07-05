import json
from unittest.mock import MagicMock

from langgraph.checkpoint.memory import MemorySaver

from opti_mind.data.models import FieldSemantics, OptimizationInstance
from opti_mind.data.schema import HeuristicSchemaInterpreter
from opti_mind.data.service import DataService
from opti_mind.modeling.generator import IRGenerator
from opti_mind.ontology.models import ProblemSpecification, ProblemType
from opti_mind.ontology.service import OntologyService
from opti_mind.workflow.clarification import ClarificationResponse
from opti_mind.workflow.context import WorkflowDependencies, default_workflow_dependencies
from opti_mind.workflow.engine import build_optimization_graph

FIXTURE = "tests/fixtures/facility_location.csv"


def test_optimization_graph_runs_to_completion() -> None:
    graph = build_optimization_graph()
    config = {"configurable": {"thread_id": "test-completion"}}
    result = graph.invoke(
        {"errors": [], "source": FIXTURE},
        config=config,
    )
    assert isinstance(result, dict)
    # data_intelligence node should have produced an instance
    assert result.get("problem_type") == "facility_location"


def test_optimization_graph_missing_source_reports_error() -> None:
    graph = build_optimization_graph()
    config = {"configurable": {"thread_id": "test-missing-source"}}
    result = graph.invoke({"errors": []}, config=config)
    assert result.get("errors")


def test_modeling_clarification_interrupt_and_resume(monkeypatch) -> None:
    """A modeling-layer missing parameter should trigger interrupt+resume."""
    from langgraph.types import Command

    base_deps = default_workflow_dependencies()

    class MissingCijGenerator(IRGenerator):
        """IRGenerator that reports c_ij missing the first time it runs."""

        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def generate_from_state_with_diagnostics(self, state: dict) -> dict:
            self.calls += 1
            knowledge = base_deps.ontology_service.retrieve(
                ProblemSpecification(problem_type=ProblemType.FACILITY_LOCATION)
            )
            instance = OptimizationInstance.model_validate(state["instance"])
            ir = self.generate(knowledge, instance)
            if self.calls == 1:
                return {
                    "ir": ir,
                    "missing_parameters": ["c_ij"],
                    "assumptions": [],
                    "used_llm": False,
                    "confidence": 1.0,
                }
            return {
                "ir": ir,
                "missing_parameters": [],
                "assumptions": [],
                "used_llm": False,
                "confidence": 1.0,
            }

    custom_ir = MissingCijGenerator()
    # Use a deterministic heuristic schema interpreter so the test is stable
    # across environments and does not accidentally fill c_ij before the gap
    # detection node can observe the missing parameter.
    data_service = DataService(schema_interpreter=HeuristicSchemaInterpreter())
    deps = WorkflowDependencies(
        data_service=data_service,
        ontology_service=base_deps.ontology_service,
        ir_generator=custom_ir,
        model_validator=base_deps.model_validator,
        solver_router=base_deps.solver_router,
        decision_service=base_deps.decision_service,
        memory_saver=base_deps.memory_saver,
        knowledge_retriever=base_deps.knowledge_retriever,
    )
    graph = build_optimization_graph(deps=deps)
    config = {"configurable": {"thread_id": "test-modeling-clarify-f"}}

    events = list(
        graph.stream(
            {"errors": [], "source": FIXTURE, "problem_type": "facility_location"},
            config=config,
        )
    )
    interrupt_event = events[-1]
    assert "__interrupt__" in interrupt_event
    req = interrupt_event["__interrupt__"][0].value
    assert req.station == "modeling"
    assert req.expected_field == "c_ij"

    response = ClarificationResponse(
        station="modeling",
        expected_field="c_ij",
        answer=json.dumps({"f1": 1.0, "f2": 1.0}),
    )
    result = graph.invoke(
        Command(resume=response.model_dump()),
        config=config,
    )
    assert result.get("ir") is not None
    assert result.get("errors") == []


def test_no_interrupt_when_heuristic_succeeds() -> None:
    """With LLM switches off, the graph should run to completion."""
    graph = build_optimization_graph()
    config = {"configurable": {"thread_id": "test-no-interrupt"}}
    events = list(
        graph.stream(
            {"errors": [], "source": FIXTURE, "problem_type": "facility_location"},
            config=config,
        )
    )
    assert not any("__interrupt__" in event for event in events)


def test_solver_node_forwards_error_from_solution() -> None:
    """If the solver router returns a result with an error field, _solver_node
    should forward that message in the errors list while keeping the solution.
    """
    from opti_mind.workflow import engine as engine_mod

    fake_result = {
        "status": "solver_unavailable",
        "objective_value": None,
        "variables": {},
        "error": "solver is not available",
    }
    fake_router = MagicMock()
    fake_router.solve_dict.return_value = fake_result
    deps = WorkflowDependencies(
        data_service=MagicMock(),
        ontology_service=MagicMock(),
        ir_generator=MagicMock(),
        model_validator=MagicMock(),
        solver_router=fake_router,
        decision_service=MagicMock(),
        memory_saver=MagicMock(),
        knowledge_retriever=MagicMock(),
    )

    state = {
        "verified_ir": {"problem_type": "facility_location", "variables": [], "constraints": []},
    }
    result = engine_mod._solver_node(state, deps)
    assert result["solution"] == fake_result
    assert any("solver is not available" in err for err in result["errors"])


def test_knowledge_retrieval_uses_ontology_service() -> None:
    """Knowledge retrieval should use ontology_service.retrieve."""
    from opti_mind.workflow import engine as engine_mod

    deps = default_workflow_dependencies()
    result = engine_mod._knowledge_retrieval_node({"problem_type": "facility_location"}, deps)
    assert result.get("errors") == []
    kp = result.get("knowledge_package")
    assert kp is not None
    assert kp["problem_type"] == "facility_location"
    assert kp["ontology_entry"]["parameters"] != {}


def test_data_intelligence_skips_confirmed_missing_clarification(monkeypatch) -> None:
    """If a role is in confirmed_missing_roles, data_intelligence should not interrupt."""
    from opti_mind.workflow import engine as engine_mod
    from opti_mind.workflow.clarification import ClarificationRequest

    deps = default_workflow_dependencies()

    class _AlwaysAskInterpreter:
        def interpret(self, columns, profile):
            return [FieldSemantics(column=c, semantic_role="other") for c in columns]

        def check_clarification(self, columns, semantics, problem_type=None):
            return ClarificationRequest(
                station="data_intelligence",
                question="Which column is c_ij?",
                options=[],
                expected_field="c_ij",
                context={"target_role": "cost", "missing_role": "cost"},
            )

    def _fake_interrupt(_req):
        raise AssertionError("interrupt should not be called for confirmed-missing role")

    monkeypatch.setattr(engine_mod, "interrupt", _fake_interrupt)

    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1"], "J": ["f1"]},
        parameters={"c_ij": {"c1": {"f1": 5.0}}},
    )
    state = {
        "source": FIXTURE,
        "problem_type": "facility_location",
        "instance": instance.model_dump(mode="json"),
        "confirmed_missing_roles": ["cost"],
        "errors": [],
    }
    result = engine_mod._data_intelligence_node(state, deps)

    assert result.get("errors") == []
    assert result["instance"]["parameters"]["c_ij"] == {"c1": {"f1": 5.0}}


def test_apply_modeling_clarification_unknown_symbol_stored_as_is() -> None:
    """Unknown parameter symbols should be stored under their canonical name."""
    from opti_mind.workflow import engine as engine_mod

    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1"], "J": ["f1"], "K": ["k1", "k2"]},
        parameters={},
    )
    response = ClarificationResponse(
        station="modeling",
        expected_field="x_k",
        answer=json.dumps({"k1": 5.0, "k2": 7.0}),
    )
    patched = engine_mod._apply_modeling_clarification(instance, response)
    assert patched.parameters["x_k"] == {"k1": 5.0, "k2": 7.0}
    assert "x" not in patched.parameters


def test_apply_modeling_clarification_default_for_unknown_symbol() -> None:
    """The default value generator should work for arbitrary indexed symbols."""
    from opti_mind.workflow import engine as engine_mod

    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1", "c2"], "J": ["f1"]},
        parameters={},
    )
    response = ClarificationResponse(
        station="modeling",
        expected_field="r_ij",
        answer="default",
    )
    patched = engine_mod._apply_modeling_clarification(instance, response)
    assert patched.parameters["r_ij"] == {
        "c1": {"f1": 0.0},
        "c2": {"f1": 0.0},
    }


def test_apply_modeling_clarification_nested_list_matrix() -> None:
    """LLM-provided row-major nested lists should be flattened and shaped."""
    from opti_mind.workflow import engine as engine_mod

    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1", "c2", "c3"], "J": ["f1", "f2", "f3"]},
        parameters={},
    )
    response = ClarificationResponse(
        station="modeling",
        expected_field="c_ij",
        answer=json.dumps([[1.0, 2.0, 5.0], [4.0, 2.0, 5.0], [3.0, 2.0, 4.0]]),
    )
    patched = engine_mod._apply_modeling_clarification(instance, response)
    assert patched.parameters["c_ij"] == {
        "c1": {"f1": 1.0, "f2": 2.0, "f3": 5.0},
        "c2": {"f1": 4.0, "f2": 2.0, "f3": 5.0},
        "c3": {"f1": 3.0, "f2": 2.0, "f3": 4.0},
    }


def test_dependency_injection_uses_provided_services() -> None:
    """build_optimization_graph should use injected fakes instead of real backends."""
    fake_df = MagicMock()
    fake_df.columns = ["col1"]

    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["a"]},
        parameters={"x": 1.0},
        meta={"dataset_id": "test", "ontology_defaults": {"x": 0.0}},
    )
    semantics = [
        FieldSemantics(
            column="col1",
            semantic_role="parameter",
            optimization_symbol="x",
            confidence=1.0,
        )
    ]

    data_service = MagicMock()
    data_service.load_df.return_value = fake_df
    data_service.profiler.profile.return_value = {}
    schema_interp = MagicMock(spec=["interpret"])
    schema_interp.interpret.return_value = semantics
    data_service.schema_interpreter = schema_interp
    data_service.rebuild_instance.return_value = instance

    ontology_service = MagicMock(spec=OntologyService)
    ontology_service.detect.return_value = MagicMock(
        model_dump=lambda mode=None: {
            "problem_type": "facility_location",
            "confidence": 1.0,
            "candidates": [],
        }
    )
    knowledge_pkg = MagicMock()
    knowledge_pkg.model_dump.return_value = {"problem_type": "facility_location"}
    ontology_service.retrieve.return_value = knowledge_pkg

    ir_model = MagicMock()
    ir_model.model_dump_safe.return_value = {
        "problem_type": "facility_location",
        "variables": [],
        "constraints": [],
    }
    ir_generator = MagicMock()
    ir_generator.generate_from_state_with_diagnostics.return_value = {
        "missing_parameters": [],
        "ir": ir_model,
    }

    verification_report = MagicMock()
    verification_report.passed = True
    verification_report.failures = []
    verification_report.model_dump.return_value = {"passed": True}
    model_validator = MagicMock()
    model_validator.validate_dict.return_value = verification_report

    solver_router = MagicMock()
    solver_router.solve_dict.return_value = {
        "status": "ok",
        "objective_value": 42.0,
        "variables": {},
        "error": None,
    }

    decision_report = MagicMock()
    decision_report.model_dump.return_value = {"recommendation": "yes"}
    decision_service = MagicMock()
    decision_service.analyze.return_value = decision_report

    fake_deps = WorkflowDependencies(
        data_service=data_service,
        ontology_service=ontology_service,
        ir_generator=ir_generator,
        model_validator=model_validator,
        solver_router=solver_router,
        decision_service=decision_service,
        memory_saver=MemorySaver(),
        knowledge_retriever=MagicMock(),
    )

    graph = build_optimization_graph(deps=fake_deps)
    config = {"configurable": {"thread_id": "test-di"}}
    result = graph.invoke({"errors": [], "source": "dummy.csv"}, config=config)

    assert isinstance(result, dict)
    fake_deps.data_service.load_df.assert_called_once_with("dummy.csv")
    fake_deps.solver_router.solve_dict.assert_called_once()
    assert result.get("solution") is not None

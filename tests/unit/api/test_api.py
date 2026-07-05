"""Tests for the optimization API endpoint."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from opti_mind.config import Settings
from opti_mind.main import app
from opti_mind.ontology.models import ProblemSpecification, ProblemType
from opti_mind.solver.router import SolverRouter
from opti_mind.workflow import engine as engine_mod
from opti_mind.workflow.context import WorkflowDependencies, default_workflow_dependencies

FIXTURE = str(Path(__file__).resolve().parents[2] / "fixtures" / "facility_location.csv")

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert "available_solver_backends" in body
    assert isinstance(body["available_solver_backends"], list)


def test_optimize_success() -> None:
    response = client.post(
        "/api/v1/optimize",
        json={"source": FIXTURE},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("success", "partial", "error")
    assert body["problem_type"] == "facility_location"
    assert "data_intelligence" in body["execution_graph"]


def test_optimize_missing_source() -> None:
    response = client.post(
        "/api/v1/optimize",
        json={"source": ""},
    )
    assert response.status_code in (200, 422)


def test_optimize_invalid_source() -> None:
    response = client.post(
        "/api/v1/optimize",
        json={"source": "/nonexistent/path/file.csv"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("error", "partial")
    assert len(body["errors"]) > 0


def test_optimize_with_business_goal() -> None:
    response = client.post(
        "/api/v1/optimize",
        json={"source": FIXTURE, "business_goal": "minimize total cost"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("success", "partial")
    assert body["problem_type"] == "facility_location"


def test_optimize_awaits_input_and_resume(monkeypatch) -> None:
    """A modeling-layer missing parameter should surface via API and resume."""
    from opti_mind.data.models import OptimizationInstance
    from opti_mind.modeling.generator import IRGenerator

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
    custom_deps = WorkflowDependencies(
        data_service=base_deps.data_service,
        ontology_service=base_deps.ontology_service,
        ir_generator=custom_ir,
        model_validator=base_deps.model_validator,
        solver_router=base_deps.solver_router,
        decision_service=base_deps.decision_service,
        memory_saver=base_deps.memory_saver,
        knowledge_retriever=base_deps.knowledge_retriever,
    )

    monkeypatch.setattr(
        engine_mod,
        "get_settings",
        lambda: Settings(llm_model_generator=True),
    )
    monkeypatch.setattr(
        engine_mod,
        "default_workflow_dependencies",
        lambda: custom_deps,
    )

    response = client.post(
        "/api/v1/optimize",
        json={"source": FIXTURE, "problem_type": "facility_location"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_input"
    assert body["clarification_request"]["station"] == "modeling"
    thread_id = body["thread_id"]

    resume_response = client.post(
        f"/api/v1/optimize/{thread_id}/resume",
        json={
            "station": "modeling",
            "expected_field": "c_ij",
            "answer": json.dumps({"c1": {"f1": 1.0, "f2": 1.0}, "c2": {"f1": 1.0, "f2": 1.0}}),
        },
    )
    assert resume_response.status_code == 200
    resume_body = resume_response.json()
    assert resume_body["status"] in ("success", "partial")
    assert resume_body["analysis_report"] is not None


def test_optimize_returns_ir_and_solution(monkeypatch) -> None:
    """The /optimize endpoint should expose the generated IR and solver solution."""
    base_deps = default_workflow_dependencies()
    mock_solver_router = SolverRouter()
    mock_solver_router._settings = Settings(solver_backend="highs")
    custom_deps = WorkflowDependencies(
        data_service=base_deps.data_service,
        ontology_service=base_deps.ontology_service,
        ir_generator=base_deps.ir_generator,
        model_validator=base_deps.model_validator,
        solver_router=mock_solver_router,
        decision_service=base_deps.decision_service,
        memory_saver=base_deps.memory_saver,
        knowledge_retriever=base_deps.knowledge_retriever,
    )

    monkeypatch.setattr(
        engine_mod,
        "get_settings",
        lambda: Settings(llm_schema_interpreter=False, llm_model_generator=False),
    )
    monkeypatch.setattr(
        engine_mod,
        "default_workflow_dependencies",
        lambda: custom_deps,
    )

    fixture = str(Path(__file__).resolve().parents[2] / "fixtures" / "facility_location.csv")
    response = client.post(
        "/api/v1/optimize",
        json={"source": fixture, "problem_type": "facility_location"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("success", "partial")
    assert body["ir"] is not None
    assert body["solution"] is not None
    assert isinstance(body["ir"], dict)
    assert isinstance(body["solution"], dict)


def test_problem_types_endpoint() -> None:
    """GET /problem-types should return a non-empty list of problem types."""
    response = client.get("/api/v1/problem-types")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0
    assert all("value" in pt and "label" in pt for pt in body)


def test_problem_type_detail_endpoint() -> None:
    """GET /problem-types/{value} should return full metadata."""
    response = client.get("/api/v1/problem-types/facility_location")
    assert response.status_code == 200
    body = response.json()
    assert body["value"] == "facility_location"
    assert "parameters" in body
    assert "variables" in body
    assert "constraints" in body


def test_problem_type_detail_not_found() -> None:
    """GET /problem-types/{value} should 404 for unknown problem types."""
    response = client.get("/api/v1/problem-types/unknown_type")
    assert response.status_code == 404

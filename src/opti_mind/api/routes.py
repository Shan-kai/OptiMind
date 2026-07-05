"""API routes for OptiMind optimization pipeline."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.types import Command
from pydantic import BaseModel, Field

from opti_mind.decision.models import AnalysisReport
from opti_mind.ontology.service import (
    IOntologyService,
    OntologyService,
    ProblemTypeDetail,
    ProblemTypeInfo,
)
from opti_mind.workflow.clarification import ClarificationResponse
from opti_mind.workflow.engine import build_optimization_graph

router = APIRouter(prefix="/api/v1", tags=["optimization"])


class OptimizeRequest(BaseModel):
    """Request model for the optimization endpoint."""

    source: str = Field(
        ...,
        description="Path or identifier of the data source (CSV file, etc.)",
    )
    problem_type: str | None = Field(
        default=None,
        description="Optional problem type hint (e.g., facility_location)",
    )
    business_goal: str = Field(
        default="",
        description="User's business objective in natural language",
    )
    scenarios: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Optional what-if scenarios for decision analysis",
    )


class OptimizeResponse(BaseModel):
    """Response model for the optimization endpoint."""

    status: str = Field(
        ...,
        description="Execution status: success, error, awaiting_input, or partial",
    )
    thread_id: str | None = Field(default=None, description="Thread ID for interrupt/resume")
    problem_type: str | None = Field(default=None, description="Detected problem type")
    analysis_report: dict[str, Any] | None = Field(
        default=None,
        description="Decision intelligence analysis report",
    )
    clarification_request: dict[str, Any] | None = Field(
        default=None,
        description="Clarification request when awaiting human input",
    )
    errors: list[str] = Field(default_factory=list, description="Pipeline errors")
    execution_graph: list[str] = Field(
        default_factory=list,
        description="Ordered list of pipeline stages executed",
    )
    ir: dict[str, Any] | None = Field(
        default=None,
        description="Final IR used for solving (verified_ir preferred, fallback to ir)",
    )
    solution: dict[str, Any] | None = Field(
        default=None,
        description="Complete optimal solution returned by the solver",
    )


def _ontology_service_dep() -> IOntologyService:
    """Dependency factory for the ontology service.

    FastAPI dependency injection does not accept default arguments, so this
    factory returns a callable that FastAPI can use as a default.
    """
    return OntologyService()


_ONTOLOGY_SERVICE: IOntologyService | None = None


def _ontology_service_singleton() -> IOntologyService:
    """Return a lazily-initialized ontology service singleton."""
    global _ONTOLOGY_SERVICE
    if _ONTOLOGY_SERVICE is None:
        _ONTOLOGY_SERVICE = OntologyService()
    return _ONTOLOGY_SERVICE


@router.get("/problem-types", response_model=list[ProblemTypeInfo])
async def list_problem_types(
    ontology_service: IOntologyService = Depends(_ontology_service_singleton),  # noqa: B008
) -> list[ProblemTypeInfo]:
    """Return all registered optimization problem types.

    The frontend uses this to populate the problem-type selector, so the
    dropdown stays in sync with the ontology YAML files.
    """
    return ontology_service.list_types()


@router.get("/problem-types/{value}", response_model=ProblemTypeDetail)
async def get_problem_type_detail(
    value: str,
    ontology_service: IOntologyService = Depends(_ontology_service_singleton),  # noqa: B008
) -> ProblemTypeDetail:
    """Return full self-describing metadata for a single problem type."""
    detail = ontology_service.get_detail(value)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Problem type '{value}' not found",
        )
    return detail


def _extract_ir(result: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the final IR from pipeline output.

    Prefers the verified IR when available; otherwise returns the raw IR.
    """
    return result.get("verified_ir") or result.get("ir")


def _extract_solution(result: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the solver solution from pipeline output."""
    return result.get("solution")


def _extract_errors(result: dict[str, Any]) -> list[str]:
    """Extract pipeline errors, including any solver-level error message.

    The solver router may return a structured ``solver_unavailable`` result
    with an ``error`` field; surface that message in the API errors list even
    if downstream nodes reset ``state['errors']``.
    """
    errors: list[str] = list(result.get("errors") or [])
    solution = _extract_solution(result)
    if solution and isinstance(solution, dict):
        solver_error = solution.get("error")
        if solver_error and not any(solver_error in existing for existing in errors):
            errors.append(solver_error)
    return errors


def _build_execution_graph(result: dict[str, Any]) -> list[str]:
    """Derive which pipeline stages produced output from the final state."""
    stages: list[str] = []
    if result.get("instance") is not None:
        stages.append("data_intelligence")
    if result.get("knowledge_package") is not None:
        stages.append("knowledge_retrieval")
    if result.get("ir") is not None:
        stages.append("modeling")
    if result.get("verification_report") is not None:
        stages.append("verification")
    if result.get("solution") is not None:
        stages.append("solver")
    if result.get("report") is not None:
        stages.append("decision")
    return stages


def _extract_report(result: dict[str, Any]) -> dict[str, Any] | None:
    """Extract and validate the analysis report from pipeline output."""
    report_data = result.get("report")
    if report_data is None:
        return None
    report = AnalysisReport.model_validate(report_data)
    return report.model_dump()


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize(request: OptimizeRequest) -> OptimizeResponse:
    """Run the full optimization pipeline.

    Executes the end-to-end workflow:
    1. Data Intelligence - ingest raw data and build optimization instance
    2. Knowledge Retrieval - classify problem and retrieve templates
    3. Modeling - generate IR model from knowledge and instance
    4. Verification - validate model structure
    5. Solver - solve using CPLEX or mock solver
    6. Decision Intelligence - analyze results and generate recommendations
    """
    initial_state: dict[str, Any] = {
        "errors": [],
        "source": request.source,
        "business_goal": request.business_goal,
        "scenarios": request.scenarios,
    }
    if request.problem_type:
        initial_state["problem_type"] = request.problem_type

    thread_id = str(uuid4())
    graph = build_optimization_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # Use stream() so we can detect interrupts (__interrupt__ events).
        result: dict[str, Any] = {}
        for event in graph.stream(initial_state, config=config):
            if "__interrupt__" in event:
                interrupt_data = event["__interrupt__"][0]
                clarification = interrupt_data.value
                clarification_request = (
                    clarification.model_dump()
                    if hasattr(clarification, "model_dump")
                    else dict(clarification)
                )
                return OptimizeResponse(
                    status="awaiting_input",
                    thread_id=thread_id,
                    problem_type=None,
                    analysis_report=None,
                    clarification_request=clarification_request,
                    errors=[],
                    execution_graph=[],
                    ir=None,
                    solution=None,
                )
            # Merge node updates into the final state. Streamed events are
            # keyed by node name, so we flatten each node's update dict.
            if isinstance(event, dict):
                for node_update in event.values():
                    if isinstance(node_update, dict):
                        result.update(node_update)
    except Exception as exc:
        return OptimizeResponse(
            status="error",
            thread_id=thread_id,
            problem_type=None,
            analysis_report=None,
            errors=[str(exc)],
            execution_graph=[],
            ir=None,
            solution=None,
        )

    errors = _extract_errors(result)
    report = _extract_report(result)
    execution_graph = _build_execution_graph(result)
    ir = _extract_ir(result)
    solution = _extract_solution(result)

    has_report = report is not None
    has_critical_errors = bool(errors) and not has_report

    if has_critical_errors:
        return OptimizeResponse(
            status="error",
            thread_id=thread_id,
            problem_type=result.get("problem_type"),
            analysis_report=None,
            errors=errors,
            execution_graph=execution_graph,
            ir=ir,
            solution=solution,
        )

    return OptimizeResponse(
        status="success" if has_report else "partial",
        thread_id=thread_id,
        problem_type=result.get("problem_type"),
        analysis_report=report,
        errors=errors,
        execution_graph=execution_graph,
        ir=ir,
        solution=solution,
    )


@router.post("/optimize/{thread_id}/resume", response_model=OptimizeResponse)
async def resume_optimization(thread_id: str, response: ClarificationResponse) -> OptimizeResponse:
    """Resume an optimization pipeline that was interrupted for clarification."""
    thread_id = thread_id.strip()
    graph = build_optimization_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = graph.invoke(
            Command(resume=response.model_dump()),
            config=config,
        )
    except Exception as exc:
        return OptimizeResponse(
            status="error",
            thread_id=thread_id,
            problem_type=None,
            analysis_report=None,
            errors=[str(exc)],
            execution_graph=[],
            ir=None,
            solution=None,
        )

    errors = _extract_errors(result)
    report = _extract_report(result)
    execution_graph = _build_execution_graph(result)
    ir = _extract_ir(result)
    solution = _extract_solution(result)

    has_report = report is not None
    has_critical_errors = bool(errors) and not has_report

    if has_critical_errors:
        return OptimizeResponse(
            status="error",
            thread_id=thread_id,
            problem_type=result.get("problem_type"),
            analysis_report=None,
            errors=errors,
            execution_graph=execution_graph,
            ir=ir,
            solution=solution,
        )

    return OptimizeResponse(
        status="success" if has_report else "partial",
        thread_id=thread_id,
        problem_type=result.get("problem_type"),
        analysis_report=report,
        errors=errors,
        execution_graph=execution_graph,
        ir=ir,
        solution=solution,
    )

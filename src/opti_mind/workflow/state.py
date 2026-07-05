"""Workflow state - single source of truth for the pipeline."""

from __future__ import annotations

from typing import Any, TypedDict


class WorkflowState(TypedDict, total=False):
    """Shared state for the end-to-end optimization pipeline."""

    source: str | None
    dataset_id: str | None
    problem_type: str | None
    instance: dict[str, Any] | None
    knowledge_package: dict[str, Any] | None
    ir: dict[str, Any] | None
    verification_report: dict[str, Any] | None
    verified_ir: dict[str, Any] | None
    solution: dict[str, Any] | None
    report: dict[str, Any] | None
    errors: list[str]

    # Human-in-the-loop: a station may suspend execution by raising a
    # ClarificationRequest and waiting for clarification_response.
    pending_clarification: dict[str, Any] | None
    clarification_response: dict[str, Any] | None

    # Optional flag: when True, force ontology-driven knowledge retrieval
    # even if the LLM model generator is enabled.
    use_ontology: bool | None

    # Ontology-driven problem type detection result.
    problem_type_match: dict[str, Any] | None

    # Gap report produced by gap_detection and consumed by ontology_patch.
    gap_report: dict[str, Any] | None

    # Missing parameters diagnosed by the modeling node for gap_detection.
    missing_parameters: list[str] | None

    # Routing hint set by nodes and read by conditional edges.
    next_node: str | None

    # Audit trail of assumptions made by ontology patches.
    assumptions: list[str]

    # LLM augmentation context carried through the pipeline.
    field_semantics: list[dict[str, Any]] | None
    business_goal: str | None
    scenarios: list[dict[str, Any]] | None

    # Agentic field mapping state.
    field_mapping_proposal: dict[str, Any] | None
    field_mapping_confirmed: bool | None
    confirmed_missing_roles: list[str] | None

    # Agentic modeling flag: when True, the modeling gap is surfaced to the
    # chat layer instead of raising a legacy modeling clarification interrupt.
    use_modeling_agent: bool | None

    # Session / chat history for the conversational frontend.
    session_id: str | None
    chat_history: list[dict[str, Any]] | None

    # Agentic orchestrator memory for parameter values provided by the user.
    last_provided_parameters: dict[str, Any] | None

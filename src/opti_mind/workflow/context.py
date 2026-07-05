"""Workflow dependency container.

The container keeps the workflow engine decoupled from concrete service
implementations, making nodes testable without real backends.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from opti_mind.data.service import DataService
from opti_mind.decision.service import DecisionService
from opti_mind.knowledge.retriever import KnowledgeRetriever
from opti_mind.modeling.generator import IRGenerator
from opti_mind.ontology.service import IOntologyService, OntologyService
from opti_mind.solver.router import SolverRouter
from opti_mind.verification.validator import ModelValidator

CHECKPOINT_DB_PATH = Path("sessions/checkpoints.sqlite")


def _create_checkpoint_saver() -> BaseCheckpointSaver[Any]:
    """Create a checkpoint saver based on settings.

    When ``persist_checkpoints`` is enabled, writes to SQLite so sessions survive
    server reloads. Otherwise uses an in-memory saver for test isolation.
    """
    from opti_mind.config import get_settings
    from opti_mind.workflow.clarification import ClarificationRequest

    serde = JsonPlusSerializer().with_msgpack_allowlist([ClarificationRequest])

    if get_settings().persist_checkpoints:
        try:
            CHECKPOINT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(CHECKPOINT_DB_PATH), check_same_thread=False)
            return SqliteSaver(conn, serde=serde)
        except Exception:  # noqa: BLE001
            pass
    return MemorySaver(serde=serde)


@dataclass
class WorkflowDependencies:
    """Injectable dependencies used by workflow nodes.

    All fields are concrete service instances so that nodes can be exercised
    with real backends in production or with fakes/MagicMocks in tests.
    """

    data_service: DataService
    ontology_service: IOntologyService
    ir_generator: IRGenerator
    model_validator: ModelValidator
    solver_router: SolverRouter
    decision_service: DecisionService
    memory_saver: BaseCheckpointSaver[Any]
    # Deprecated: kept for backwards compatibility during migration.
    knowledge_retriever: KnowledgeRetriever = field(
        default_factory=KnowledgeRetriever,
        repr=False,
    )


_DEFAULT_DEPS: WorkflowDependencies | None = None


def default_workflow_dependencies() -> WorkflowDependencies:
    """Build the default dependency set used by ``build_optimization_graph``.

    The default container is lazily initialized and reused across calls so
    that ``build_optimization_graph()`` behaves identically to the previous
    module-level singleton implementation (e.g. shared checkpoint memory).
    """
    global _DEFAULT_DEPS
    if _DEFAULT_DEPS is None:
        ontology_service = OntologyService()
        _DEFAULT_DEPS = WorkflowDependencies(
            data_service=DataService(),
            ontology_service=ontology_service,
            ir_generator=IRGenerator(),
            model_validator=ModelValidator(),
            solver_router=SolverRouter(),
            decision_service=DecisionService(),
            memory_saver=_create_checkpoint_saver(),
            knowledge_retriever=KnowledgeRetriever(),
        )
    return _DEFAULT_DEPS

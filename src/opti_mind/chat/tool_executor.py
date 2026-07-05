"""Helpers for orchestrator-driven field mapping.

The executor is stateless: every tool call receives the current workflow state
and returns a JSON-serializable result dict. State mutations are collected in
``state_updates`` and applied by the caller.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from opti_mind.data.models import (
    CanonicalRole,
    FieldMappingProposal,
    OptimizationInstance,
    SchemaMappingProposal,
)
from opti_mind.data.schema import HeuristicSchemaInterpreter
from opti_mind.data.service import DataService

logger = logging.getLogger(__name__)


class FieldMappingToolExecutor:
    """Execute mapping updates and build proposals for the orchestrator."""

    def __init__(self, deps: Any | None = None) -> None:
        self.deps = deps

    def execute(
        self,
        tool: str,
        input_data: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch a tool call to the appropriate handler."""
        handler: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = getattr(
            self, f"_{tool}", None
        )
        if handler is None:
            return {"status": "error", "error": f"Unknown tool: {tool}"}
        try:
            return handler(input_data, state)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Tool %s failed", tool)
            return {"status": "error", "error": f"{tool}: {exc}"}

    def _update_mapping(self, input_data: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """Update the mapping proposal and rebuild the instance."""
        proposal_data = state.get("field_mapping_proposal")
        if not proposal_data:
            return {"status": "error", "error": "No mapping proposal exists yet."}

        proposal = SchemaMappingProposal.model_validate(proposal_data)
        updates = input_data.get("updates", [])
        for upd in updates:
            column = upd.get("column")
            if not column:
                continue
            field = proposal.get_field(column)
            if field is None:
                field = FieldMappingProposal(column=column)
                proposal.fields.append(field)
            if "canonical_role" in upd and upd["canonical_role"]:
                try:
                    field.canonical_role = CanonicalRole(upd["canonical_role"])
                except ValueError:
                    field.canonical_role = CanonicalRole.OTHER
            if "semantic_role" in upd:
                field.semantic_role = upd["semantic_role"]
            if "optimization_symbol" in upd:
                field.optimization_symbol = upd["optimization_symbol"]
            if "is_index" in upd:
                field.is_index = bool(upd["is_index"])

        source = self._require_source(state)
        df = self._load_df(source)
        semantics = proposal.to_field_semantics_list()
        instance = self._rebuild_instance(df, semantics, state)

        return {
            "status": "ok",
            "result": {
                "updated_columns": [u.get("column") for u in updates if u.get("column")],
                "proposal": proposal.model_dump(mode="json"),
            },
            "state_updates": {
                "field_mapping_proposal": proposal.model_dump(mode="json"),
                "field_semantics": [s.model_dump(mode="json") for s in semantics],
                "instance": instance.model_dump(mode="json"),
            },
        }

    def _heuristic_proposal(
        self,
        columns: list[str],
        profile: Any,
        problem_type_hint: str | None = None,
    ) -> SchemaMappingProposal:
        """Build a heuristic mapping proposal from column names and profile."""
        from opti_mind.data.models import DataProfileReport
        from opti_mind.data.schema import HeuristicSchemaInterpreter

        interpreter = HeuristicSchemaInterpreter()
        profile_report = DataProfileReport.model_validate(profile)
        semantics = interpreter.interpret(columns, profile_report)
        fields = []
        for s in semantics:
            fields.append(
                FieldMappingProposal(
                    column=s.column,
                    semantic_role=s.semantic_role,
                    optimization_symbol=s.optimization_symbol,
                    canonical_role=s.canonical_role,
                    is_index=s.is_index,
                )
            )
        return SchemaMappingProposal(
            problem_type=problem_type_hint,
            fields=fields,
            overall_reasoning="Heuristic mapping from column names.",
        )

    def _rebuild_instance(
        self,
        df: Any,
        semantics: list[Any],
        state: dict[str, Any],
    ) -> OptimizationInstance:
        """Rebuild the optimization instance from field semantics."""
        data_service = DataService()
        dataset_id = Path(str(state.get("source", "dataset"))).stem
        instance = data_service.rebuild_instance(
            df,
            semantics,
            dataset_id=dataset_id,
            problem_type=state.get("problem_type"),
        )

        # Preserve manually-provided parameters that the updated data still lacks.
        old_instance_data = state.get("instance")
        if old_instance_data:
            try:
                old_instance = OptimizationInstance.model_validate(old_instance_data)
                for key, value in old_instance.parameters.items():
                    if key not in instance.parameters:
                        instance.parameters[key] = value
            except Exception:  # noqa: BLE001
                pass

        # Also replay parameters from last_provided_parameters if still missing.
        last_provided = state.get("last_provided_parameters") or {}
        for symbol, value in last_provided.items():
            if symbol not in instance.parameters:
                instance.parameters[symbol] = value

        return instance

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_source(self, state: dict[str, Any]) -> str:
        source = state.get("source")
        if not source:
            raise ValueError("No source available in state")
        return str(source)

    def _load_df(self, source: str) -> Any:
        return DataService().load_df(source)

    def _schema_interpreter(self, state: dict[str, Any]) -> Any:
        """Return the schema interpreter from deps or a default one."""
        if self.deps is not None and hasattr(self.deps, "data_service"):
            return self.deps.data_service.schema_interpreter
        return HeuristicSchemaInterpreter()

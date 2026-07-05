"""Tools for the LLM-driven optimization orchestrator.

These tools give a single LLM agent full control over the conversational flow:
analyze data, confirm/update mappings, submit missing parameters, run the
pipeline, ask the user, or inspect current status. All side effects are returned
as JSON-serializable `state_updates` so the generic `AgentLoop` can apply them.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langgraph.types import Command
from pydantic import BaseModel, Field

from opti_mind.chat.modeling_tool_executor import canonicalize_symbol
from opti_mind.chat.tool_executor import FieldMappingToolExecutor
from opti_mind.chat.types import ToolDefinition
from opti_mind.config import get_settings
from opti_mind.data.keyword_mapping import get_canonical_role
from opti_mind.data.models import OptimizationInstance
from opti_mind.data.service import DataService
from opti_mind.ontology.service import IOntologyService, OntologyService
from opti_mind.workflow.clarification import ClarificationRequest, ClarificationResponse
from opti_mind.workflow.engine import build_optimization_graph

logger = logging.getLogger(__name__)


class AnalyzeDataInput(BaseModel):
    """No inputs required; analyze_data uses the current state."""

    pass


class ConfirmMappingInput(BaseModel):
    """Confirm the current field mapping proposal."""

    pass


class UpdateMappingInput(BaseModel):
    """Update one or more column mappings."""

    updates: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of {column, canonical_role, optimization_symbol, ...} updates.",
    )


class SubmitParametersInput(BaseModel):
    """Submit parameter values as a symbol -> JSON value dict."""

    parameters: dict[str, Any] = Field(
        description="E.g. {'f_j': [5.0,6.0,8.0], 'c_ij': [[1,2],[3,4]]}"
    )


class RunPipelineInput(BaseModel):
    """Run the optimization pipeline."""

    pass


class AskUserInput(BaseModel):
    """Ask the user a clarifying question."""

    question: str = Field(description="Chinese question to show the user.")


class GetStatusInput(BaseModel):
    """Return the current session status without side effects."""

    pass


ORCHESTRATOR_TOOL_DEFINITIONS: list[ToolDefinition] = [
    ToolDefinition(
        name="analyze_data",
        description="Read the uploaded CSV and propose a field-to-model mapping.",
        input_schema=AnalyzeDataInput.model_json_schema(),
    ),
    ToolDefinition(
        name="confirm_mapping",
        description="Confirm the current field mapping proposal.",
        input_schema=ConfirmMappingInput.model_json_schema(),
    ),
    ToolDefinition(
        name="update_mapping",
        description="Update one or more column mappings and rebuild the instance.",
        input_schema=UpdateMappingInput.model_json_schema(),
    ),
    ToolDefinition(
        name="submit_parameters",
        description="Submit one or more missing parameter values as JSON.",
        input_schema=SubmitParametersInput.model_json_schema(),
    ),
    ToolDefinition(
        name="run_pipeline",
        description="Run the optimization pipeline and report success, interrupt, or error.",
        input_schema=RunPipelineInput.model_json_schema(),
    ),
    ToolDefinition(
        name="ask_user",
        description="Ask the user a clarifying question and wait for their reply.",
        input_schema=AskUserInput.model_json_schema(),
    ),
    ToolDefinition(
        name="get_status",
        description="Inspect current mapping, missing parameters, and pipeline stage.",
        input_schema=GetStatusInput.model_json_schema(),
    ),
]


class OrchestratorToolExecutor:
    """Execute tools requested by the optimization orchestrator agent."""

    def __init__(
        self,
        ontology_service: IOntologyService | None = None,
        data_service: DataService | None = None,
    ) -> None:
        self.ontology_service = ontology_service or OntologyService()
        self.data_service = data_service or DataService()
        self._field_executor = FieldMappingToolExecutor()

    def execute(
        self,
        tool_call: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch an orchestrator tool call."""
        tool = tool_call.get("tool", "")
        input_data = tool_call.get("input", {})
        handler: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = getattr(
            self, f"_{tool}", None
        )
        if handler is None:
            return {"status": "error", "error": f"Unknown tool: {tool}"}
        try:
            return handler(input_data, state)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Orchestrator tool %s failed", tool)
            return {"status": "error", "error": f"{tool}: {exc}"}

    def _analyze_data(self, _input: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """Propose a field mapping and build an initial instance."""
        source = state.get("source")
        if not source:
            return {"status": "error", "error": "No source available in state"}

        df = self.data_service.load_df(str(source))
        columns = list(df.columns)
        profile = self.data_service.profiler.profile(df)

        # Prefer LLM interpreter when enabled, otherwise heuristic.
        schema_interp = self.data_service.schema_interpreter
        if get_settings().llm_schema_interpreter and hasattr(schema_interp, "propose_mapping"):
            sample_rows = df.head(get_settings().llm_orchestrator_sample_rows).to_dict(
                orient="records"
            )
            proposal = schema_interp.propose_mapping(
                columns,
                profile,
                sample_rows,
                problem_type_hint=state.get("problem_type"),
            )
        else:
            proposal = self._field_executor._heuristic_proposal(
                columns, profile, state.get("problem_type")
            )

        semantics = proposal.to_field_semantics_list()
        instance = self.data_service.rebuild_instance(
            df,
            semantics,
            dataset_id=Path(str(source)).stem,
            problem_type=state.get("problem_type"),
        )

        # Preserve manually-provided parameters across re-analysis. The CSV may
        # not contain columns for parameters like c_ij, so a fresh rebuild would
        # lose them and the agent would ask again.
        old_instance_data = state.get("instance")
        if old_instance_data:
            try:
                old_instance = OptimizationInstance.model_validate(old_instance_data)
                for key, value in old_instance.parameters.items():
                    if key not in instance.parameters:
                        instance.parameters[key] = value
            except Exception:  # noqa: BLE001
                pass

        for symbol, value in (state.get("last_provided_parameters") or {}).items():
            if symbol not in instance.parameters:
                instance.parameters[symbol] = value

        # Attach ontology entry so downstream tools can resolve aliases.
        problem_type = state.get("problem_type") or instance.problem_type
        entry = self._get_ontology_entry(problem_type)
        if entry is not None:
            instance.meta["ontology_entry"] = entry.model_dump(mode="json")

        missing = self._missing_parameters(instance, problem_type)

        return {
            "status": "ok",
            "result": {
                "proposal": proposal.model_dump(mode="json"),
                "missing_parameters": missing,
                "problem_type": problem_type,
            },
            "state_updates": {
                "field_mapping_proposal": proposal.model_dump(mode="json"),
                "field_semantics": [s.model_dump(mode="json") for s in semantics],
                "instance": instance.model_dump(mode="json"),
                "problem_type": problem_type,
                "missing_parameters": missing,
            },
        }

    def _confirm_mapping(self, _input: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """Mark the current mapping as confirmed."""
        if not state.get("field_mapping_proposal"):
            return {"status": "error", "error": "No mapping proposal to confirm"}
        return {
            "status": "ok",
            "result": {"confirmed": True},
            "state_updates": {"field_mapping_confirmed": True},
        }

    def _update_mapping(self, input_data: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """Update the mapping proposal and rebuild the instance."""
        result = self._field_executor.execute(
            "update_mapping",
            input_data,
            state,
        )
        # Recompute missing parameters against the rebuilt instance.
        instance_data = result.get("state_updates", {}).get("instance")
        if instance_data is not None:
            instance = OptimizationInstance.model_validate(instance_data)
            problem_type = state.get("problem_type") or instance.problem_type
            missing = self._missing_parameters(instance, problem_type)
            result.setdefault("state_updates", {})["missing_parameters"] = missing
            result.setdefault("result", {})["missing_parameters"] = missing
        return result

    def _submit_parameters(
        self, input_data: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply user-provided parameter values to the instance."""
        parameters = input_data.get("parameters", {})
        if not parameters:
            return {"status": "error", "error": "No parameters provided"}

        instance_data = state.get("instance")
        if not instance_data:
            return {
                "status": "error",
                "error": "No instance available; call analyze_data first.",
            }

        updated_instance = OptimizationInstance.model_validate(instance_data)
        provided_symbols: list[str] = []
        failed: list[str] = []
        for raw_symbol, value in parameters.items():
            symbol = canonicalize_symbol(raw_symbol, state)
            answer = json.dumps(value) if not isinstance(value, str) else value
            from opti_mind.workflow.clarification import ClarificationResponse
            from opti_mind.workflow.engine import _apply_modeling_clarification

            response = ClarificationResponse(
                station="modeling",
                expected_field=symbol,
                answer=answer,
            )
            try:
                updated_instance = _apply_modeling_clarification(updated_instance, response)
                provided_symbols.append(symbol)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to apply parameter %s: %s", symbol, exc)
                failed.append(symbol)

        missing = [s for s in state.get("missing_parameters") or [] if s not in provided_symbols]

        last_provided = dict(state.get("last_provided_parameters") or {})
        confirmed_missing = list(state.get("confirmed_missing_roles") or [])
        for symbol in provided_symbols:
            value = updated_instance.parameters.get(symbol)
            if value is not None:
                last_provided[symbol] = value
            for role in self._roles_for_symbol(symbol, updated_instance.problem_type):
                if role not in confirmed_missing:
                    confirmed_missing.append(role)

        state_updates: dict[str, Any] = {
            "instance": updated_instance.model_dump(mode="json"),
            "missing_parameters": missing,
            "last_provided_parameters": last_provided,
        }
        if confirmed_missing:
            state_updates["confirmed_missing_roles"] = confirmed_missing

        # If the user just answered a pending pipeline clarification, clear it.
        pending = state.get("pending_clarification")
        if pending and isinstance(pending, dict):
            pending_field = pending.get("expected_field", "")
            pending_role = (
                pending.get("context", {}).get("target_role")
                or pending.get("context", {}).get("missing_role")
                or ""
            )
            resolved = pending_field in provided_symbols or any(
                pending_role in self._roles_for_symbol(s, updated_instance.problem_type)
                for s in provided_symbols
            )
            if resolved:
                state_updates["pending_clarification"] = None

        return {
            "status": "ok" if not failed else "error",
            "result": {"provided": provided_symbols, "failed": failed},
            "state_updates": state_updates,
        }

    def _run_pipeline(self, _input: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """Run the optimization pipeline and report the outcome."""
        session_id = state.get("session_id")
        if not session_id:
            return {"status": "error", "error": "No session_id in state"}

        graph = build_optimization_graph()
        config = {"configurable": {"thread_id": session_id}}

        # The orchestrator may have just applied state updates (e.g. submitted
        # parameter values) that only exist in its local state. Sync them to the
        # shared checkpoint so the pipeline sees the latest instance, mapping, and
        # missing_parameters.
        try:
            graph.update_state(config, state)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not sync orchestrator state to checkpoint: %s", exc)

        confirmed_missing = list(state.get("confirmed_missing_roles") or [])
        max_auto_resumes = (len(confirmed_missing) + 1) if confirmed_missing else 1
        current_input: Any = None
        interrupt_req: Any | None = None
        for _ in range(max_auto_resumes):
            interrupt_req = None
            for event in graph.stream(current_input, config=config):
                if "__interrupt__" in event:
                    interrupt_req = event["__interrupt__"][0].value
                    break

            if interrupt_req is None:
                break

            req = (
                interrupt_req
                if isinstance(interrupt_req, ClarificationRequest)
                else ClarificationRequest.model_validate(interrupt_req)
            )

            # Auto-resume confirmed-missing data_intelligence clarifications.
            confirmed_missing_set = set(confirmed_missing)
            interrupt_role = req.context.get("target_role") or req.context.get("missing_role") or ""
            if (
                confirmed_missing
                and req.station == "data_intelligence"
                and (
                    req.expected_field in confirmed_missing_set
                    or interrupt_role in confirmed_missing_set
                )
            ):
                current_input = Command(
                    resume=ClarificationResponse(
                        station="data_intelligence",
                        expected_field=req.expected_field,
                        answer="__missing__",
                        context=req.context,
                    ).model_dump()
                )
                continue
            break

        final_state = dict(graph.get_state(config).values)

        if interrupt_req is not None:
            req = (
                interrupt_req
                if isinstance(interrupt_req, ClarificationRequest)
                else ClarificationRequest.model_validate(interrupt_req)
            )
            state_updates = self._state_updates_from_pipeline(final_state)
            state_updates["pending_clarification"] = req.model_dump()
            return {
                "status": "awaiting_input",
                "result": {
                    "station": req.station,
                    "expected_field": req.expected_field,
                    "question": req.question,
                    "options": [opt.model_dump() for opt in req.options],
                },
                "state_updates": state_updates,
                "ask_user": True,
            }

        errors = list(final_state.get("errors") or [])
        solution = final_state.get("solution")
        report = final_state.get("report")
        pipeline_status = "success" if report is not None else ("error" if errors else "incomplete")

        state_updates = self._state_updates_from_pipeline(final_state)
        state_updates["pending_clarification"] = None
        return {
            "status": pipeline_status,
            "result": {
                "errors": errors,
                "has_solution": solution is not None,
                "has_report": report is not None,
            },
            "state_updates": state_updates,
        }

    def _ask_user(self, input_data: dict[str, Any], _state: dict[str, Any]) -> dict[str, Any]:
        """Return a question that ends the current turn."""
        return {
            "status": "ok",
            "result": {"question": input_data.get("question", "")},
            "ask_user": True,
        }

    def _get_status(self, _input: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """Return a snapshot of current session state."""
        proposal = state.get("field_mapping_proposal")
        instance_data = state.get("instance")
        instance_params: dict[str, Any] = {}
        if instance_data:
            try:
                instance = OptimizationInstance.model_validate(instance_data)
                instance_params = dict(instance.parameters)
            except Exception:  # noqa: BLE001
                pass

        return {
            "status": "ok",
            "result": {
                "field_mapping_confirmed": bool(state.get("field_mapping_confirmed")),
                "has_mapping_proposal": proposal is not None,
                "missing_parameters": list(state.get("missing_parameters") or []),
                "instance_parameters": instance_params,
                "last_provided_parameters": dict(state.get("last_provided_parameters") or {}),
                "pipeline_stages": self._pipeline_stages(state),
                "pending_clarification": state.get("pending_clarification"),
            },
        }

    @staticmethod
    def _state_updates_from_pipeline(final_state: dict[str, Any]) -> dict[str, Any]:
        """Pick the keys that should be synced back to the orchestrator state."""
        keys = [
            "instance",
            "knowledge_package",
            "ir",
            "verified_ir",
            "verification_report",
            "solution",
            "report",
            "errors",
            "missing_parameters",
            "pending_clarification",
            "gap_report",
            "problem_type",
            "dataset_id",
            "last_provided_parameters",
        ]
        return {k: final_state[k] for k in keys if k in final_state}

    @staticmethod
    def _pipeline_stages(state: dict[str, Any]) -> list[str]:
        """Return which pipeline stages have produced outputs."""
        stages: list[str] = []
        if state.get("instance") is not None:
            stages.append("data_intelligence")
        if state.get("knowledge_package") is not None:
            stages.append("knowledge_retrieval")
        if state.get("ir") is not None or state.get("verified_ir") is not None:
            stages.append("modeling")
        if state.get("verification_report") is not None:
            stages.append("verification")
        if state.get("solution") is not None:
            stages.append("solver")
        if state.get("report") is not None:
            stages.append("decision")
        return stages

    def _get_ontology_entry(self, problem_type: str | None) -> Any | None:
        """Return the ontology entry for a problem type, or None."""
        if not problem_type:
            return None
        try:
            return self.ontology_service.get_entry(problem_type)
        except Exception:  # noqa: BLE001
            return None

    def _roles_for_symbol(self, symbol: str, problem_type: str | None) -> list[str]:
        """Return canonical roles associated with a parameter symbol.

        When a user provides a parameter value directly (e.g. c_ij) it means the
        corresponding column is absent from their CSV. Mapping the symbol back to
        its canonical role lets the pipeline auto-resume the data_intelligence
        clarification with ``__missing__`` instead of asking again.
        """
        entry = self._get_ontology_entry(problem_type)
        if entry is None:
            return []
        base = symbol.split("_", 1)[0] if "_" in symbol else symbol
        keyword_aliases = (entry.metadata or {}).get("keyword_aliases", {})
        keywords: list[str] = keyword_aliases.get(base, [])
        roles: list[str] = []
        for keyword in keywords:
            role = get_canonical_role(keyword)
            if role is not None and str(role) not in roles:
                roles.append(str(role))
        return roles

    def _missing_parameters(
        self, instance: OptimizationInstance, problem_type: str | None
    ) -> list[str]:
        """Compare instance parameters to ontology required parameters."""
        if not problem_type:
            return []
        entry = self._get_ontology_entry(problem_type)
        if entry is None:
            return []

        sig = entry.signature or {}
        required = set(sig.get("required_parameters", []))
        if not required:
            required = set(entry.parameters.keys())

        present = set(instance.parameters.keys())
        present_bases = {p.split("_", 1)[0] for p in present if "_" in p}
        present_bases.update(p for p in present if "_" not in p)

        missing: list[str] = []
        for symbol in required:
            base = symbol.split("_", 1)[0] if "_" in symbol else symbol
            if symbol not in present and base not in present_bases:
                missing.append(symbol)

        # The backend automatically computes parameters declared in the ontology
        # (e.g. big-M constants for inventory and scheduling); they are not
        # user-facing parameters.
        auto_computed = set(sig.get("auto_computed_parameters", []))
        return [s for s in missing if s not in auto_computed]


def execute_orchestrator_tool_call(
    tool_call: dict[str, Any],
    state: dict[str, Any],
    ontology_service: IOntologyService | None = None,
    data_service: DataService | None = None,
) -> dict[str, Any]:
    """Convenience wrapper around OrchestratorToolExecutor.execute()."""
    executor = OrchestratorToolExecutor(
        ontology_service=ontology_service,
        data_service=data_service,
    )
    return executor.execute(tool_call, state)

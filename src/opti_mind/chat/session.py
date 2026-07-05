"""AgentSession: product runtime layer for conversational OptiMind sessions.

This module owns:

- Session state access (LangGraph checkpoint)
- Agent routing (orchestrator → decision agent)
- Pipeline execution via the optimization graph
- Chat history mutations
- JSONL event logging

It intentionally does not know about FastAPI / HTTP.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langgraph.types import Command

from opti_mind.chat.decision_agent import DecisionAgent
from opti_mind.chat.i18n import CHAT_STRINGS
from opti_mind.chat.models import ChatActionResult, ChatMessage, SessionResponse
from opti_mind.chat.orchestrator import OptimizationOrchestrator
from opti_mind.chat.session_logger import (
    SessionEvent,
    SessionLogger,
    convert_agent_events,
)
from opti_mind.chat.session_logger import (
    session_logger as default_session_logger,
)
from opti_mind.config import get_settings
from opti_mind.data.keyword_mapping import get_canonical_role
from opti_mind.data.models import OptimizationInstance
from opti_mind.workflow.clarification import ClarificationRequest, ClarificationResponse
from opti_mind.workflow.engine import (
    _apply_modeling_clarification,
    _extract_numbers_from_text,
    build_optimization_graph,
)

logger = logging.getLogger(__name__)


class AgentSessionError(Exception):
    """Raised when an AgentSession operation cannot be completed."""


class AgentSession:
    """Manage the lifecycle of a single conversational optimization session.

    Args:
        session_id: Unique session identifier.
        graph: Optional pre-built optimization graph. A new one is built if omitted.
        config: Optional LangGraph checkpoint config.
            Defaults to ``{"configurable": {"thread_id": session_id}}``.
        logger: Optional session logger. Defaults to the shared JSONL logger.
        orchestrator: Optional OptimizationOrchestrator instance. If omitted, one
            is created lazily when orchestrator mode is enabled.
        decision_agent: Optional DecisionAgent instance. If omitted, one is created
            lazily when decision analysis is enabled.
    """

    def __init__(
        self,
        session_id: str,
        graph: Any | None = None,
        config: dict[str, Any] | None = None,
        logger: SessionLogger | None = None,
        orchestrator: OptimizationOrchestrator | None = None,
        decision_agent: DecisionAgent | None = None,
    ) -> None:
        self.session_id = session_id
        self.graph = graph if graph is not None else build_optimization_graph()
        self.config = config if config is not None else {"configurable": {"thread_id": session_id}}
        self.logger = logger if logger is not None else default_session_logger
        self._orchestrator = orchestrator
        self._decision_agent = decision_agent

    @property
    def orchestrator(self) -> OptimizationOrchestrator:
        """Lazily instantiate OptimizationOrchestrator."""
        if self._orchestrator is None:
            self._orchestrator = OptimizationOrchestrator()
        return self._orchestrator

    @property
    def decision_agent(self) -> DecisionAgent:
        """Lazily instantiate DecisionAgent."""
        if self._decision_agent is None:
            self._decision_agent = DecisionAgent()
        return self._decision_agent

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    def create(self, initial_state: dict[str, Any]) -> dict[str, Any]:
        """Create the session checkpoint and run any agentic startup stages."""
        try:
            self._run_graph(initial_state)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Session startup failed")
            raise AgentSessionError(f"startup: {exc}") from exc

        state = self.get_state()
        try:
            state = self._process_agentic_turn(user_message="")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agentic startup failed")
            raise AgentSessionError(f"agentic_startup: {exc}") from exc

        self._log_response(state)
        return state

    def chat(self, user_message: str) -> dict[str, Any]:
        """Append a user message and run the appropriate agent stage."""
        state = self.get_state()
        if not state:
            raise AgentSessionError("session_not_found")

        self._append_user_message(user_message)

        try:
            state = self._process_agentic_turn(user_message=user_message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Chat turn failed")
            raise AgentSessionError(f"chat: {exc}") from exc

        self._log_response(state)
        return state

    def get_state(self) -> dict[str, Any]:
        """Read the latest checkpointed state as a plain dict."""
        snapshot = self.graph.get_state(self.config)
        if snapshot is None:
            return {}
        return dict(snapshot.values)

    def build_response(self, state: dict[str, Any] | None = None) -> SessionResponse:
        """Build the API response shape from the current workflow state."""
        if state is None:
            state = self.get_state()

        errors = list(state.get("errors") or [])
        report = state.get("report")
        chat_history = self._get_chat_history(state)
        pending = state.get("pending_clarification")
        ir = state.get("verified_ir") or state.get("ir")
        solution = state.get("solution")

        if solution and isinstance(solution, dict):
            solver_error = solution.get("error")
            if solver_error and not any(solver_error in existing for existing in errors):
                errors.append(solver_error)

        if errors and report is None:
            status_ = "error"
        elif pending:
            status_ = "awaiting_input"
        elif report is not None:
            status_ = "success"
        else:
            status_ = "created"

        return SessionResponse(
            session_id=self.session_id,
            status=status_,
            messages=[ChatMessage.model_validate(m) for m in chat_history],
            clarification_request=pending,
            analysis_report=report,
            execution_graph=self._build_execution_graph(state),
            errors=errors,
            ir=ir,
            solution=solution,
            instance=state.get("instance"),
        )

    # ------------------------------------------------------------------
    # Agent routing
    # ------------------------------------------------------------------

    def _process_agentic_turn(self, user_message: str) -> dict[str, Any]:
        """Route the turn through the orchestrator or decision agent."""
        if self._should_run_decision_agent():
            result = self._run_decision_agent(user_message)
            self._apply_agent_result(result)
            return self.get_state()

        if self._orchestrator is not None or get_settings().llm_orchestrator_agent:
            # Before asking the LLM, deterministically extract any parameter values
            # the user provided (e.g. "M=10000"). This prevents rigid confirmation
            # loops when the user answers a pending parameter question directly.
            state = self.get_state()
            # If the user is answering a pending data-intelligence clarification
            # (e.g. providing a missing parameter value), resume LangGraph first so
            # the interrupt does not loop forever.
            if self._maybe_resume_data_intelligence(state, user_message):
                state = self.get_state()
            self._try_apply_user_parameters(state, user_message)

            result = self._run_orchestrator_agent(user_message)
            self._apply_agent_result(result)
            return self.get_state()

        # No LLM agent enabled: deterministic pass-through.
        return self.get_state()

    def _should_run_decision_agent(self) -> bool:
        """Run the decision agent when the pipeline has produced a solution/report."""
        if self._decision_agent is None and not get_settings().llm_decision_analyzer_agent:
            return False
        state = self.get_state()
        return bool(state.get("solution") and state.get("report"))

    def _run_orchestrator_agent(self, user_message: str) -> ChatActionResult:
        state = self.get_state()
        messages = self._get_chat_history_messages()
        result = self.orchestrator.run(state, messages, user_message)
        self._log_agent_result("orchestrator", user_message, result)
        return result

    def _run_decision_agent(self, user_message: str) -> ChatActionResult:
        state = self.get_state()
        messages = self._get_chat_history_messages()
        result = self.decision_agent.run(state, messages, user_message)
        self._log_agent_result("decision_agent", user_message, result)
        return result

    def _apply_agent_result(self, result: ChatActionResult) -> None:
        """Apply state updates and append the final assistant message."""
        if result.state_updates:
            # If the pipeline is still awaiting input, do not overwrite an empty
            # missing_parameters list that the orchestrator has already cleared.
            state = self.get_state()
            updates = dict(result.state_updates)
            if (
                updates.get("pending_clarification") is not None
                and not state.get("missing_parameters")
                and "missing_parameters" in updates
            ):
                del updates["missing_parameters"]
            self.graph.update_state(self.config, updates)

        # Auto-advance the pipeline once all prerequisites are satisfied,
        # even if the LLM did not explicitly call run_pipeline.
        state = self.get_state()
        if self._should_auto_run_pipeline(state):
            self._run_graph(None)
            state = self.get_state()

        message = result.final_message
        if not message:
            missing = state.get("missing_parameters")
            if missing:
                message = (
                    f"我还需要参数 **{missing[0]}** 的值。\n"
                    "请直接提供数值，例如向量 `5,6,8` 或矩阵 `1,2,3;4,5,6;7,8,9`；"
                    "如果之前已经提供过，可以回复“和上次一样”。"
                )
            elif (
                not state.get("field_mapping_confirmed")
                and state.get("field_mapping_proposal") is not None
            ):
                message = CHAT_STRINGS.format_mapping_proposal(state["field_mapping_proposal"])
        if message:
            self._append_assistant_message(message)

    def _try_apply_user_parameters(
        self, state: dict[str, Any], user_message: str
    ) -> dict[str, Any]:
        """Deterministically parse parameter values from the user message.

        If the user replies with a value for a currently missing parameter
        (e.g. ``M=10000`` or ``c_ij:1,2,3;4,5,6;7,8,9``), apply it directly
        without waiting for the LLM orchestrator. This prevents rigid
        mapping-then-parameter ordering loops.
        """
        instance_data = state.get("instance")
        if not instance_data:
            return {}
        try:
            instance = OptimizationInstance.model_validate(instance_data)
        except Exception:  # noqa: BLE001
            return {}

        missing = list(state.get("missing_parameters") or [])
        if not missing:
            return {}

        provided_symbols: list[str] = []
        last_provided = dict(state.get("last_provided_parameters") or {})
        confirmed_missing = list(state.get("confirmed_missing_roles") or [])

        for symbol in missing:
            value = self._extract_parameter_value(symbol, user_message, instance)
            if value is None:
                continue

            response = ClarificationResponse(
                station="modeling",
                expected_field=symbol,
                answer=json.dumps(value),
            )
            try:
                instance = _apply_modeling_clarification(instance, response)
                provided_symbols.append(symbol)
                last_provided[symbol] = instance.parameters.get(symbol)
                for role in self._roles_for_symbol(symbol, instance):
                    if role not in confirmed_missing:
                        confirmed_missing.append(role)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Deterministic parameter apply failed for %s: %s", symbol, exc)

        if not provided_symbols:
            return {}

        updates: dict[str, Any] = {
            "instance": instance.model_dump(mode="json"),
            "missing_parameters": [s for s in missing if s not in provided_symbols],
            "last_provided_parameters": last_provided,
        }
        if confirmed_missing:
            updates["confirmed_missing_roles"] = confirmed_missing

        # If a mapping proposal exists, automatically confirm it so the
        # pipeline can proceed once the missing parameters are supplied.
        if state.get("field_mapping_proposal") is not None and not state.get(
            "field_mapping_confirmed"
        ):
            updates["field_mapping_confirmed"] = True

        # Clear a pending modeling clarification that was just resolved.
        pending = state.get("pending_clarification")
        if pending and isinstance(pending, dict):
            pending_field = pending.get("expected_field", "")
            if pending_field in provided_symbols:
                updates["pending_clarification"] = None

        self.graph.update_state(self.config, updates)
        return updates

    def _extract_parameter_value(
        self, symbol: str, user_message: str, instance: OptimizationInstance
    ) -> Any | None:
        """Extract a value for ``symbol`` from ``user_message`` if present.

        Supports ``M=10000``, ``M: 10000``, ``f_j: 5,6,8``,
        ``c_ij:1,2,3;4,5,6;7,8,9`` and base-name aliases such as ``c: ...``
        when the canonical missing symbol is ``c_ij``.
        """
        candidates = {symbol}
        base = symbol.split("_", 1)[0] if "_" in symbol else symbol
        if base != symbol:
            candidates.add(base)

        for candidate in sorted(candidates, key=len, reverse=True):
            pattern = rf"{re.escape(candidate)}\s*[:=：]\s*([^。！？\n]+)"
            match = re.search(pattern, user_message)
            if not match:
                continue
            raw = match.group(1).strip()
            if not raw:
                continue
            parsed = _extract_numbers_from_text(raw)
            if parsed != raw:
                return parsed
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw

        return None

    @staticmethod
    def _roles_for_symbol(symbol: str, instance: OptimizationInstance) -> list[str]:
        """Return canonical roles associated with a parameter symbol.

        When the user provides a parameter value directly (e.g. ``c_ij``),
        the corresponding column is absent from the CSV. Mapping the symbol
        back to its canonical role lets the pipeline auto-resume the
        data_intelligence clarification with ``__missing__``.
        """
        base = symbol.split("_", 1)[0] if "_" in symbol else symbol
        entry = instance.meta.get("ontology_entry")
        if not isinstance(entry, dict):
            return []
        keyword_aliases = (entry.get("metadata") or {}).get("keyword_aliases", {})
        keywords: list[str] = keyword_aliases.get(base, [])
        roles: list[str] = []
        for keyword in keywords:
            role = get_canonical_role(keyword)
            if role is not None and str(role) not in roles:
                roles.append(str(role))
        return roles

    def _maybe_resume_data_intelligence(
        self,
        state: dict[str, Any],
        user_message: str,
    ) -> bool:
        """Resume a pending data_intelligence interrupt when the user answered it.

        The LLM-driven data_intelligence node may raise a clarification for a
        missing column. If the user replies with a parameter value (e.g.
        ``M=10000``) or explicitly says the column is absent, we resume the
        graph with ``__missing__`` so LangGraph clears the interrupt and the
        preserved parameter value can carry the pipeline forward.
        """
        pending = state.get("pending_clarification")
        if not isinstance(pending, dict):
            return False
        if pending.get("station") != "data_intelligence":
            return False

        expected_field = pending.get("expected_field", "")
        if not self._user_message_answers_clarification(user_message, expected_field, state):
            return False

        # If the user gave a concrete value, also store it on the instance so
        # the pipeline does not need to ask again.
        instance_data = state.get("instance")
        if instance_data and expected_field:
            try:
                instance = OptimizationInstance.model_validate(instance_data)
                value = self._extract_parameter_value(expected_field, user_message, instance)
                if value is not None:
                    response = ClarificationResponse(
                        station="modeling",
                        expected_field=expected_field,
                        answer=json.dumps(value),
                    )
                    instance = _apply_modeling_clarification(instance, response)
                    last_provided = dict(state.get("last_provided_parameters") or {})
                    last_provided[expected_field] = instance.parameters.get(expected_field)
                    self.graph.update_state(
                        self.config,
                        {
                            "instance": instance.model_dump(mode="json"),
                            "last_provided_parameters": last_provided,
                        },
                    )
            except Exception:  # noqa: BLE001
                pass

        self._run_graph(
            Command(
                resume=ClarificationResponse(
                    station="data_intelligence",
                    expected_field=expected_field,
                    answer="__missing__",
                    context=pending.get("context", {}),
                ).model_dump()
            ),
            confirmed_missing=list(state.get("confirmed_missing_roles") or []),
        )
        return True

    def _user_message_answers_clarification(
        self,
        user_message: str,
        expected_field: str,
        state: dict[str, Any],
    ) -> bool:
        """Return True when the user message answers a pending clarification."""
        if not expected_field:
            return False

        instance_data = state.get("instance")
        if instance_data:
            try:
                instance = OptimizationInstance.model_validate(instance_data)
                value = self._extract_parameter_value(expected_field, user_message, instance)
                if value is not None:
                    return True
            except Exception:  # noqa: BLE001
                pass

        normalized = user_message.lower().strip()
        missing_phrases = {
            "没有",
            "none",
            "missing",
            "缺",
            "没这一列",
            "用默认值",
            "default",
            "参数",
            "数值",
        }
        return any(phrase in normalized for phrase in missing_phrases)

    @staticmethod
    def _should_auto_run_pipeline(state: dict[str, Any]) -> bool:
        """Return True when the optimization pipeline should auto-advance."""
        return (
            bool(state.get("field_mapping_confirmed"))
            and not state.get("missing_parameters")
            and not state.get("pending_clarification")
            and state.get("solution") is None
            and state.get("report") is None
        )

    # ------------------------------------------------------------------
    # Graph and chat history helpers
    # ------------------------------------------------------------------

    def _run_graph(
        self,
        input_state: dict[str, Any] | Command[Any] | None,
        *,
        confirmed_missing: list[str] | None = None,
    ) -> None:
        """Stream the graph and persist any clarification interrupt into the checkpoint.

        If a ``data_intelligence`` interrupt concerns a role the user has already
        confirmed as missing, automatically resume with ``__missing__`` so the
        pipeline can build an instance without showing a template clarification.
        """
        max_auto_resumes = (len(confirmed_missing) + 1) if confirmed_missing else 1
        current_input: Any = input_state
        for _ in range(max_auto_resumes):
            interrupt_req: Any | None = None
            for event in self.graph.stream(current_input, config=self.config):
                if "__interrupt__" in event:
                    interrupt_req = event["__interrupt__"][0].value
                    break

            if interrupt_req is None:
                return

            req = (
                interrupt_req
                if isinstance(interrupt_req, ClarificationRequest)
                else ClarificationRequest.model_validate(interrupt_req)
            )

            # Auto-resume confirmed-missing data_intelligence clarifications.
            confirmed_missing_set = set(confirmed_missing or [])
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

            # Convert any interrupt into pending state and let the orchestrator handle it.
            self._convert_interrupt_to_pending(req)
            return

    def _convert_interrupt_to_pending(self, req: ClarificationRequest) -> None:
        """Store a pipeline clarification interrupt as pending state for the orchestrator."""
        state = self.get_state()
        updates: dict[str, Any] = {"pending_clarification": req.model_dump()}
        if req.station == "data_intelligence":
            updates["field_mapping_confirmed"] = False
        elif req.station == "modeling":
            missing = list(state.get("missing_parameters") or [])
            if req.expected_field and req.expected_field not in missing:
                missing.append(req.expected_field)
            context_missing = req.context.get("missing_parameters") or ""
            for symbol in context_missing.split(","):
                symbol = symbol.strip()
                if symbol and symbol not in missing:
                    missing.append(symbol)
            updates["missing_parameters"] = missing
        self.graph.update_state(self.config, updates)

    def _get_chat_history(self, state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if state is None:
            state = self.get_state()
        return list(state.get("chat_history") or [])

    def _get_chat_history_messages(self) -> list[ChatMessage]:
        return [ChatMessage.model_validate(m) for m in self._get_chat_history()]

    def _update_chat_history(self, chat_history: list[dict[str, Any]]) -> None:
        self.graph.update_state(self.config, {"chat_history": chat_history})

    def _append_user_message(self, content: str) -> None:
        chat_history = self._get_chat_history()
        chat_history.append(ChatMessage.create("user", content).model_dump())
        self._update_chat_history(chat_history)

    def _append_assistant_message(self, content: str) -> None:
        chat_history = self._get_chat_history()
        chat_history.append(ChatMessage.create("assistant", content).model_dump())
        self._update_chat_history(chat_history)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_agent_result(
        self,
        handler: str,
        user_message: str,
        result: ChatActionResult,
    ) -> None:
        events = convert_agent_events(
            self.session_id, handler, user_message, result.events, result.final_message
        )
        self.logger.log(self.session_id, events)

    def _log_response(self, state: dict[str, Any]) -> None:
        response = self.build_response(state)
        event = SessionEvent(
            session_id=self.session_id,
            sequence=0,
            event_type="pipeline_run",
            handler="agent_session",
            payload={
                "status": response.status,
                "execution_graph": response.execution_graph,
                "has_solution": response.solution is not None,
                "has_report": response.analysis_report is not None,
            },
            errors=response.errors,
        )
        self.logger.log(self.session_id, [event])

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_execution_graph(state: dict[str, Any]) -> list[str]:
        stages: list[str] = []
        if state.get("instance") is not None:
            stages.append("data_intelligence")
        if state.get("knowledge_package") is not None:
            stages.append("knowledge_retrieval")
        if state.get("ir") is not None:
            stages.append("modeling")
        if state.get("verification_report") is not None:
            stages.append("verification")
        if state.get("solution") is not None:
            stages.append("solver")
        if state.get("report") is not None:
            stages.append("decision")
        return stages

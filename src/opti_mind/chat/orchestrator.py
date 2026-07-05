"""Optimization Orchestrator: a single LLM agent that drives the whole session.

Unlike the earlier split field-mapping / modeling agents, the orchestrator is
given a small set of high-level tools and a clear workflow. It decides when to:

- analyze the uploaded data
- confirm/update the mapping
- ask the user for missing information
- submit user-provided parameter values
- run the optimization pipeline

All state mutations flow through the tool results and are applied by the caller.
"""

from __future__ import annotations

import json
from typing import Any

from opti_mind.chat.agent_loop import AgentLoop, ToolHooks
from opti_mind.chat.models import ChatActionResult, ChatMessage
from opti_mind.chat.orchestrator_tools import (
    ORCHESTRATOR_TOOL_DEFINITIONS,
    OrchestratorToolExecutor,
)
from opti_mind.chat.resources import load_resource, render_template
from opti_mind.config import get_settings
from opti_mind.core.llm_client import ILLMClient, create_llm_client
from opti_mind.data.service import DataService
from opti_mind.ontology.service import IOntologyService, OntologyService

_SYSTEM_PROMPT_TEMPLATE = """\
You are OptiMind, a conversational optimization assistant for a Chinese user.
Drive the session forward: analyze the uploaded CSV, confirm the field mapping,
collect missing parameter values, and run the optimization pipeline.

Output ONLY a single JSON object with two fields: `final_message` (Chinese
text) and `tool_calls` (list of {tool, input}). Do NOT wrap it in markdown code
blocks.

Read the current state and follow these rules in order:
1. If `field_mapping_proposal` is null, call `analyze_data` exactly once.
2. If mapping exists but is not confirmed:
   - Do NOT ask for missing parameters yet. Only ask whether the mapping is
     correct or needs changes.
   - "确认"/"继续"/"ok"/"是的"/"没问题" → `confirm_mapping`
   - mapping change request → `update_mapping`
   - user gives a parameter value before confirming
     (e.g. "M=10000" or "f_j: 5,6,8") → `confirm_mapping` then
     `submit_parameters` in the same turn.
   - otherwise present the mapping and ask for confirmation or changes.
3. If mapping is confirmed:
   - `missing_parameters` empty → `run_pipeline`
   - user gives a numeric value for a missing symbol
     (e.g. "f_j: 5,6,8" or "c_ij:1,2,5;4,2,5;3,2,4") → `submit_parameters`
     immediately. This means the column is missing; do NOT ask for a column name.
   - "和上次一样"/"用之前的"/"沿用" and the value is in
     `last_provided_parameters` → `submit_parameters` with that stored value.
   - "确认"/"继续" with missing parameters and no stored value → `ask_user`
     for the missing value.
4. If `run_pipeline` returns `awaiting_input`, repeat the pending question and
   then `submit_parameters` or `run_pipeline`.
5. If `run_pipeline` succeeds, summarize the result briefly in Chinese.
6. If unclear, `ask_user` with a concise Chinese question.

Critical rules:
- DO NOT call `run_pipeline` unless mapping is confirmed and
  `missing_parameters` is empty (or contains only auto-computed parameters).
- DO NOT ask for missing parameters before mapping is confirmed.
- DO NOT make up values not in the state.
- DO NOT repeat already-answered questions.
- `M` is automatically computed by the backend for inventory and scheduling.
  It must NEVER be asked from the user.
- Use canonical ontology symbols in `submit_parameters` (e.g. `s_i`, `I0_i`,
  `f_j`, `c_ij`). Do NOT use invented symbols like `K_i` or `I_i^0`.
- Prefer one tool call per turn. Combine when logically necessary (e.g.
  `confirm_mapping` followed by `submit_parameters` when the user gave a value
  before confirming).

Parameter JSON formats for `submit_parameters`:
- Vector: {"f_j": [5.0, 6.0, 8.0]}
- Matrix: {"c_ij": [[1.0, 2.0, 5.0], [4.0, 2.0, 5.0], [3.0, 2.0, 4.0]]}
- Scalar: {"C": 30.0}

The backend automatically computes the big-M constant `M` for inventory and
scheduling models. `M` is NOT a user parameter and must NEVER be asked from
the user.

Available tools:
{{tool_schemas}}
"""


class OptimizationOrchestrator:
    """Single LLM agent that controls the conversational optimization flow."""

    def __init__(
        self,
        llm_client: ILLMClient | None = None,
        ontology_service: IOntologyService | None = None,
        data_service: DataService | None = None,
    ) -> None:
        self.llm_client = llm_client or create_llm_client()
        self.ontology_service = ontology_service or OntologyService()
        self.data_service = data_service or DataService()

    def run(
        self,
        state: dict[str, Any],
        chat_history: list[ChatMessage],
        user_message: str,
    ) -> ChatActionResult:
        """Run one orchestrator turn and return the result."""
        system_prompt = self._build_system_prompt()

        tool_executor = OrchestratorToolExecutor(
            ontology_service=self.ontology_service,
            data_service=self.data_service,
        )

        def executor(tool_call: dict[str, Any], local_state: dict[str, Any]) -> dict[str, Any]:
            return tool_executor.execute(tool_call, local_state)

        loop = AgentLoop(
            system_prompt=system_prompt,
            tool_executor=executor,
            llm_client=self.llm_client,
            hooks=ToolHooks(),
            max_tool_turns=get_settings().llm_orchestrator_max_tool_turns,
        )
        history = [m.model_dump() for m in chat_history]
        result = loop.run(state, history, user_message)
        return ChatActionResult(
            final_message=result.final_message,
            state_updates=result.state_updates,
            continue_pipeline=result.continue_pipeline,
            events=[e.model_dump() for e in result.events],
        )

    def _build_system_prompt(self) -> str:
        """Build the system prompt with tool schemas."""
        tool_schemas = json.dumps(
            [t.model_dump() for t in ORCHESTRATOR_TOOL_DEFINITIONS],
            ensure_ascii=False,
            indent=2,
        )
        template = load_resource("skills/orchestrator_agent.md") or _SYSTEM_PROMPT_TEMPLATE
        return render_template(
            template,
            {
                "tool_schemas": tool_schemas,
                "max_tool_turns": get_settings().llm_orchestrator_max_tool_turns,
            },
        )

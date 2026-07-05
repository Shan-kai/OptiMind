"""Decision Analysis Agent: answers post-solution questions via tools.

This agent is activated after the optimization pipeline has produced a solution
and an analysis report. It lets the user ask natural-language follow-up
questions such as "what does this result mean?", "which parameter is most
sensitive?", or "what if c_ij increases by 10%?".

All heavy lifting (sensitivity, scenario re-solve, report summarization) is done
by the deterministic decision engines through tools; the LLM only translates
results into business-friendly Chinese.
"""

from __future__ import annotations

import json
from typing import Any

from opti_mind.chat.agent_loop import AgentLoop, ToolHooks
from opti_mind.chat.decision_tools import DECISION_TOOL_DEFINITIONS, execute_decision_tool_call
from opti_mind.chat.models import ChatActionResult, ChatMessage
from opti_mind.chat.resources import load_resource, render_template
from opti_mind.config import get_settings
from opti_mind.core.llm_client import ILLMClient, create_llm_client

_SYSTEM_PROMPT_TEMPLATE = """\
You are OptiMind, a senior business analyst interpreting an optimization
solution for a Chinese user.

The optimization pipeline has already finished. Answer follow-up questions
using the provided tools. Base every statement on tool results; do not invent
numbers.

Important conventions:
- The user may refer to a single cost element as `c_11`, `c_{a1,t1}`,
  `c[a1,t1]`, or simply "a1 做 t1 的成本". All of these mean `c_ij[a1,t1]`.
- For aggregate sensitivity (e.g. "c_ij 整体是否敏感"), use
  `analyze_sensitivity`.
- For single-coefficient sensitivity (e.g. "c_11 敏感吗"), you MUST use
  `run_scenario` because MIP solvers do not provide exact dual ranges for
  individual matrix entries.

Tool usage rules:
1. `explain_solution` — objective value, solution status, or key metrics.
2. `summarize_report` — recommendations, risks, or executive summary.
3. `analyze_sensitivity` — aggregate parameter sensitivity only. It CANNOT
   compute exact intervals for a single matrix element such as `c_11` or
   `c[a1,t1]`.
4. `run_scenario` — what-if questions, including single-element changes.
   Convert natural-language changes into deterministic `changes` strings:
   - "c_ij 增加 10%" → `c_ij *= 1.1`
   - "Q_j 增加 10" → `Q_j += 10`
   - "f_j 减少 20%" → `f_j *= 0.8`
   - "c_{a1,t1} 降低 10" → `c_ij[a1,t1] -= 10`
   - "c_11 降低多少会改变方案" → run multiple scenarios such as
     `c_ij[a1,t1] -= 5`, `c_ij[a1,t1] -= 10`, `c_ij[a1,t1] -= 15`, then
     report the smallest change that alters the optimal objective or
     assignment.
5. `ask_user` — when the request is ambiguous.

Output ONLY a JSON object with `final_message` (required Chinese text) and
`tool_calls` (list of {tool, input}). Do NOT wrap it in markdown code blocks.
Do NOT leave `final_message` empty.

Available tools:
{{tool_schemas}}
"""


class DecisionAgent:
    """LLM agent that answers post-solution questions through decision tools."""

    def __init__(self, llm_client: ILLMClient | None = None) -> None:
        self.llm_client = llm_client or create_llm_client()

    def run(
        self,
        state: dict[str, Any],
        chat_history: list[ChatMessage],
        user_message: str,
    ) -> ChatActionResult:
        """Run one decision-analysis turn and return the result."""
        system_prompt = self._build_system_prompt()

        loop = AgentLoop(
            system_prompt=system_prompt,
            tool_executor=execute_decision_tool_call,
            llm_client=self.llm_client,
            hooks=ToolHooks(),
            max_tool_turns=get_settings().llm_decision_analyzer_max_tool_turns,
        )
        history = [m.model_dump() for m in chat_history]
        result = loop.run(state, history, user_message)
        final_message = result.final_message
        if not final_message:
            final_message = (
                "我已经收到你的问题，但暂时没有找到可以直接回答的数值结果。"
                "你可以换个说法，比如“c_ij[a1,t1] 降低 10 会怎样”，我会用情景模拟帮你分析。"
            )
        return ChatActionResult(
            final_message=final_message,
            state_updates=result.state_updates,
            continue_pipeline=result.continue_pipeline,
            events=[e.model_dump() for e in result.events],
        )

    def _build_system_prompt(self) -> str:
        """Build the system prompt with tool schemas."""
        tool_schemas = json.dumps(
            [t.model_dump() for t in DECISION_TOOL_DEFINITIONS],
            ensure_ascii=False,
            indent=2,
        )
        template = load_resource("skills/decision_agent.md") or _SYSTEM_PROMPT_TEMPLATE
        return render_template(
            template,
            {
                "tool_schemas": tool_schemas,
                "max_tool_turns": get_settings().llm_decision_analyzer_max_tool_turns,
            },
        )

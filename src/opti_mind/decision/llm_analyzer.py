"""LLM-backed decision analyzer for natural language business insights.

This module provides an optional enhancement step for ``DecisionService``.
After all deterministic analysis engines have run, it asks an LLM to translate
the structured report + solution into a concise business summary and
actionable recommendations. Failures are swallowed so the deterministic report
is never corrupted.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from opti_mind.core.llm_client import ILLMClient, create_llm_client
from opti_mind.decision.models import AnalysisReport
from opti_mind.modeling.ir_models import IRModel

logger = logging.getLogger(__name__)


class DecisionLLMOutput(BaseModel):
    """Expected LLM output shape for decision analysis."""

    summary: str = Field(description="Concise executive summary of the solution.")
    recommendations: list[str] = Field(
        default_factory=list,
        description="Actionable business recommendations in natural language.",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions made while generating the summary.",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the generated insights (0.0 to 1.0).",
    )


_SYSTEM_PROMPT = (
    "你是一位资深的运筹优化业务分析师，正在向中文用户解释一个数学优化模型的求解结果。"
    "请根据业务目标、求解器输出和结构化分析报告，生成一份专业、可执行的业务洞察。"
    "所有输出必须使用中文。"
    "\n\n要求："
    "\n1. 执行摘要：用 2-4 句话概括最优方案、关键指标和业务含义。"
    "\n2. AI 建议：给出 3-5 条具体、可落地的业务建议，每条一个完整的句子。"
    "   可涵盖：实施方案、成本优化、风险缓释、约束松绑、容量扩张、需求调整等。"
    "\n3. 建模假设：列出 2-4 条该分析隐含的关键假设，帮助用户理解结论边界。"
    "\n4. 返回严格的合法 JSON，不要包含任何 Markdown 代码块或额外说明。"
)


class LLMDecisionAnalyzer:
    """Enhance an AnalysisReport with LLM-generated narrative insights."""

    def __init__(self, llm_client: ILLMClient | None = None) -> None:
        self.llm_client = llm_client or create_llm_client()
        self.parser = PydanticOutputParser(pydantic_object=DecisionLLMOutput)
        self.format_instructions = self.parser.get_format_instructions()

    def enhance(
        self,
        report: AnalysisReport,
        solution: dict[str, Any],
        ir: IRModel | None,
        business_goal: str | None,
        scenarios: list[dict[str, Any]] | None,
    ) -> None:
        """Populate ``report`` with LLM summary/recommendations/assumptions.

        This method mutates ``report`` in place. Any exception is logged and
        suppressed so that the deterministic report remains usable.
        """
        try:
            prompt = self._build_prompt(report, solution, ir, business_goal, scenarios)
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response = self.llm_client.chat(messages)
            parsed: DecisionLLMOutput = self.parser.parse(response.content)
        except Exception as exc:  # noqa: BLE001 - LLM failure must not break report
            logger.warning("LLM decision analysis failed, skipping: %s", exc)
            return

        report.llm_summary = parsed.summary
        report.llm_recommendations = parsed.recommendations
        report.llm_assumptions = parsed.assumptions

        if parsed.confidence < 0.5:
            report.executive_summary += "\n\nLLM insights generated with low confidence."

    def _build_prompt(
        self,
        report: AnalysisReport,
        solution: dict[str, Any],
        ir: IRModel | None,
        business_goal: str | None,
        scenarios: list[dict[str, Any]] | None,
    ) -> str:
        """Build the user prompt for the LLM."""
        context = {
            "business_goal": business_goal or "Not provided",
            "solution": solution,
            "report": report.model_dump(exclude={"raw_solution"}),
            "ir": ir.model_dump() if ir else None,
            "scenarios": scenarios or [],
        }
        return f"Context:\n{context}\n\n" f"{self.format_instructions}"

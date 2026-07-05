"""Tests for LLMDecisionAnalyzer."""

from __future__ import annotations

import json

from opti_mind.decision.llm_analyzer import LLMDecisionAnalyzer
from opti_mind.decision.models import AnalysisReport


def _make_report() -> AnalysisReport:
    return AnalysisReport(
        status="optimal",
        objective_value=42.0,
        executive_summary="Baseline deterministic summary.",
    )


def test_llm_analyzer_enhances_report(fake_llm_client):
    """LLM output should populate llm_summary and llm_recommendations."""
    response = json.dumps(
        {
            "summary": "The solver found a cost-effective configuration.",
            "recommendations": ["Close warehouse B."],
            "assumptions": ["Demand is stable."],
            "confidence": 0.9,
        }
    )
    analyzer = LLMDecisionAnalyzer(llm_client=fake_llm_client(response))
    report = _make_report()
    analyzer.enhance(report, {"objective": 42.0}, None, "minimize cost", [])

    assert report.llm_summary == "The solver found a cost-effective configuration."
    assert report.llm_recommendations == ["Close warehouse B."]
    assert report.llm_assumptions == ["Demand is stable."]


def test_llm_analyzer_failure_keeps_deterministic_report():
    """An LLM failure must not corrupt the deterministic report."""

    class ExplodingClient:
        def chat(self, messages, **kwargs):
            raise RuntimeError("boom")

    analyzer = LLMDecisionAnalyzer(llm_client=ExplodingClient())
    report = _make_report()
    analyzer.enhance(report, {"objective": 42.0}, None, None, None)

    assert report.llm_summary == ""
    assert report.llm_recommendations == []
    assert report.executive_summary == "Baseline deterministic summary."

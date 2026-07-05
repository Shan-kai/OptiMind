"""Decision package smoke tests."""

from __future__ import annotations

from opti_mind.decision import AnalysisReport, DecisionService


def test_imports() -> None:
    assert AnalysisReport is not None
    assert DecisionService is not None

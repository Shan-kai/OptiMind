"""Schema Understanding: map column names to optimization semantics.

Phase 2 uses a heuristic fallback so the pipeline runs without a live LLM.
A real LLM-backed interpreter can be plugged in via create_schema_interpreter.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from opti_mind.config import get_settings
from opti_mind.data.keyword_mapping import (
    get_canonical_role,
    get_semantic_role_and_symbol,
    is_index_keyword,
)
from opti_mind.data.llm_interpreter import LLMSchemaInterpreter
from opti_mind.data.models import DataProfileReport, FieldSemantics


@runtime_checkable
class ISchemaInterpreter(Protocol):
    """Understand column semantics from profile + column names."""

    def interpret(self, columns: list[str], profile: DataProfileReport) -> list[FieldSemantics]: ...


class HeuristicSchemaInterpreter:
    """Deterministic fallback interpreter. No LLM required."""

    def interpret(self, columns: list[str], profile: DataProfileReport) -> list[FieldSemantics]:
        out: list[FieldSemantics] = []
        for col in columns:
            key = str(col).lower().strip()
            role, symbol = get_semantic_role_and_symbol(key)
            canonical = get_canonical_role(key)
            out.append(
                FieldSemantics(
                    column=str(col),
                    semantic_role=role,
                    optimization_symbol=symbol,
                    confidence=1.0,
                    canonical_role=canonical,
                    is_index=is_index_keyword(key),
                )
            )
        return out


def create_schema_interpreter(
    use_llm: bool | None = None,
) -> ISchemaInterpreter:
    """Factory: select heuristic or LLM-backed schema interpreter.

    Args:
        use_llm: True -> LLM; False -> heuristic; None -> read from config.
    """
    if use_llm is None:
        use_llm = get_settings().llm_schema_interpreter
    if use_llm:
        return LLMSchemaInterpreter()
    return HeuristicSchemaInterpreter()


__all__ = [
    "ISchemaInterpreter",
    "HeuristicSchemaInterpreter",
    "create_schema_interpreter",
]

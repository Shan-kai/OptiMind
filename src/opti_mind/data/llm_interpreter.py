"""LLM-backed schema interpreter using a pluggable ILLMClient.

This module provides an alternative to the heuristic schema interpreter.
It sends column names and basic statistics to an LLM and asks it to map each
column to its optimization semantics.

Deterministic First: the LLM call is wrapped so that any failure (network,
timeout, parsing) silently falls back to the heuristic interpreter instead of
aborting the pipeline. After interpretation, check_clarification() inspects
the result for missing critical roles / low confidence and may emit a
ClarificationRequest for the human-in-the-loop mini-agent.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from opti_mind.chat.i18n import CHAT_STRINGS
from opti_mind.core.llm_client import ILLMClient, create_llm_client
from opti_mind.data.keyword_mapping import (
    get_canonical_role,
    get_semantic_role_and_symbol,
    is_index_keyword,
)
from opti_mind.data.models import (
    CanonicalRole,
    DataProfileReport,
    FieldMappingProposal,
    FieldSemantics,
    SchemaMappingProposal,
)
from opti_mind.ontology.models import ProblemType
from opti_mind.ontology.repository import OntologyRepository
from opti_mind.workflow.clarification import ClarificationOption, ClarificationRequest

logger = logging.getLogger(__name__)

# Semantic roles whose absence is most likely to break downstream modeling.
# Each canonical textual role is mapped to its CanonicalRole so that checks work
# regardless of whether the LLM returns a terse or descriptive semantic_role.
_CRITICAL_ROLES: dict[str, CanonicalRole] = {
    "demand": CanonicalRole.DEMAND,
    "capacity": CanonicalRole.CAPACITY,
    "cost": CanonicalRole.COST,
}
_CONFIDENCE_THRESHOLD = 0.5

# Problem-type-aware mapping from ontology parameter symbols to the canonical
# role that can satisfy them.  Used so a column mapped to the role (e.g.
# CAPACITY) does not trigger a clarification for the canonical symbol
# (e.g. C for knapsack).
_PARAM_ROLE_MAP: dict[str, dict[str, CanonicalRole]] = {
    "facility_location": {
        "d_i": CanonicalRole.DEMAND,
        "Q_j": CanonicalRole.CAPACITY,
        "f_j": CanonicalRole.FIXED_COST,
        "c_ij": CanonicalRole.COST,
    },
    "assignment": {"c_ij": CanonicalRole.COST},
    "transportation": {
        "s_i": CanonicalRole.SUPPLY,
        "d_j": CanonicalRole.DEMAND,
        "c_ij": CanonicalRole.COST,
    },
    "knapsack": {
        "v_i": CanonicalRole.VALUE,
        "w_i": CanonicalRole.WEIGHT,
        "C": CanonicalRole.CAPACITY,
    },
    "scheduling": {
        "p_j": CanonicalRole.PROCESSING_TIME,
        "d_j": CanonicalRole.DUE_DATE,
        "w_j": CanonicalRole.WEIGHT,
    },
    "inventory": {
        "d_it": CanonicalRole.DEMAND,
        "h_i": CanonicalRole.HOLDING_COST,
        "s_i": CanonicalRole.ORDERING_COST,
        "c_i": CanonicalRole.PURCHASE_COST,
        "I0_i": CanonicalRole.INITIAL_INVENTORY,
    },
    "network_flow": {
        "c_ij": CanonicalRole.COST,
        "u_ij": CanonicalRole.CAPACITY,
    },
}

# Reverse mapping for generic critical-role fallback so that a patched column
# gets a concrete optimization_symbol the FeatureMapper can use.
_ROLE_SYMBOL_HINTS: dict[str, str] = {
    "demand": "d_i",
    "capacity": "Q_j",
    "cost": "c_ij",
}
_SYMBOL_ROLE_HINTS: dict[str, str] = {
    "d_i": "demand",
    "Q_j": "capacity",
    "f_j": "fixed_cost",
    "c_ij": "cost",
    "s_i": "supply",
    "d_j": "demand",
    "u_ij": "capacity",
    "b_i": "balance",
    "p_j": "processing_time",
    "w_j": "weight",
    "K_i": "fixed_cost",
    "h_i": "holding_cost",
    "v_i": "value",
    "w_i": "weight",
}

# Canonical optimization_symbol for each (problem_type, canonical_role).
# This overrides any non-standard symbol the LLM might invent (e.g. K_i -> s_i).
_CANONICAL_SYMBOLS: dict[tuple[str, str], str] = {
    (problem, role.value): symbol
    for problem, role_map in _PARAM_ROLE_MAP.items()
    for symbol, role in role_map.items()
}
# Add explicit role->symbol mappings for roles whose base name collides.
_CANONICAL_SYMBOLS.update(
    {
        ("inventory", "ordering_cost"): "s_i",
        ("inventory", "purchase_cost"): "c_i",
        ("inventory", "initial_inventory"): "I0_i",
        ("facility_location", "fixed_cost"): "f_j",
        ("facility_location", "cost"): "c_ij",
        ("scheduling", "due_date"): "d_j",
    }
)


class SchemaInterpretation(BaseModel):
    """Expected LLM output shape for schema interpretation."""

    fields: list[FieldSemantics] = Field(
        description="List of field semantics for every input column, including ids and names.",
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of the mapping decisions.",
    )


class _MappingProposalOutput(BaseModel):
    """Expected LLM output shape for the full mapping proposal."""

    problem_type: str | None = Field(
        default=None,
        description="Detected optimization problem type, e.g. facility_location.",
    )
    fields: list[FieldMappingProposal] = Field(
        description="Mapping proposal for every input column.",
    )
    overall_reasoning: str = Field(
        default="",
        description="Brief Chinese explanation of the overall mapping logic.",
    )


_SYSTEM_PROMPT = (
    "You are an operations-research expert. Analyze the provided CSV column "
    "names and their statistical profiles, then map each column to its role in "
    "a mathematical optimization model. "
    "For every column, return a FieldSemantics object with: \n"
    "- column: exact input name\n"
    "- semantic_role: business meaning, or null if irrelevant\n"
    "- optimization_symbol: standard notation like d_i, f_j, c_ij, or null\n"
    "- confidence: 0.0 to 1.0; use < 0.5 when uncertain\n"
    "- canonical_role: one of customer_key, facility_key, agent_key, task_key, "
    "source_key, sink_key, demand, supply, capacity, fixed_cost, cost, "
    "distance, value, weight, processing_time, due_date, holding_cost, "
    "ordering_cost, purchase_cost, initial_inventory, ignore, other\n"
    "- is_index: true only if this column identifies a set member "
    "(e.g. customer id, facility id)\n"
    "Use null for both semantic_role and optimization_symbol when the column "
    "is not a model parameter."
)

_MAPPING_PROPOSAL_SYSTEM_PROMPT = (
    "You are an operations-research expert assisting a Chinese user. Analyze "
    "the provided CSV column names, sample rows, and statistical profiles, "
    "then propose a complete field-to-model mapping.\n\n"
    "Return a JSON object with:\n"
    "- problem_type: the detected optimization problem type "
    "(e.g. facility_location, transportation, knapsack)\n"
    "- fields: one FieldMappingProposal per input column\n"
    "- overall_reasoning: a one-sentence Chinese explanation of the mapping "
    "logic\n\n"
    "Each FieldMappingProposal must include:\n"
    "- column: exact input name\n"
    "- canonical_role: one of the allowed values; use 'ignore' for "
    "irrelevant columns\n"
    "- semantic_role: short business meaning (null for ignored columns)\n"
    "- optimization_symbol: standard notation like d_i, f_j, c_ij "
    "(null for ignored columns)\n"
    "- confidence: 0.0 to 1.0; be conservative and use < 0.5 when unsure\n"
    "- chinese_label: short Chinese label shown to the user\n"
    "- reasoning: one-line Chinese reason for the mapping\n"
    "- is_index: true only if this column identifies a set member "
    "(e.g. customer id, facility id)\n\n"
    "Important:\n"
    "- Mark index/identifier columns (customer, facility, agent, task, source, "
    "sink, item, job, period, node) as is_index=true.\n"
    "- Mark purely descriptive or unrelated columns as canonical_role='ignore'.\n"
    "- Do not guess: if a column could be multiple roles, pick the most likely "
    "one and lower the confidence.\n"
    "- optimization_symbol MUST be the canonical ontology symbol for the role "
    "(e.g. ordering_cost -> s_i, initial_inventory -> I0_i, fixed_cost -> f_j). "
    "Do NOT invent symbols like K_i or I_i^0.\n"
    "- M (big-M) is automatically computed by the backend for inventory and "
    "scheduling; it is NEVER a user-facing parameter and must not be asked for."
)


class LLMSchemaInterpreter:
    """Interpret CSV column semantics using an LLM.

    The LLM client is pluggable via ILLMClient, so you can use Kimi, OpenAI,
    Ollama, or any custom provider without changing this code.
    """

    def __init__(self, llm_client: ILLMClient | None = None) -> None:
        self.llm_client = llm_client or create_llm_client()
        self.parser = PydanticOutputParser(pydantic_object=SchemaInterpretation)
        self.format_instructions = self.parser.get_format_instructions()
        self.proposal_parser = PydanticOutputParser(pydantic_object=_MappingProposalOutput)
        self.proposal_format_instructions = self.proposal_parser.get_format_instructions()

    def interpret(
        self,
        columns: list[str],
        profile: DataProfileReport,
    ) -> list[FieldSemantics]:
        """Map columns to optimization semantics using the LLM.

        Falls back to the heuristic interpreter if the LLM call or output
        parsing fails, so the pipeline is never blocked by an LLM outage.

        Args:
            columns: List of column names from the dataset.
            profile: Statistical profile produced by DataProfiler.

        Returns:
            A list of FieldSemantics, one per input column.
        """
        try:
            prompt = self._build_prompt(columns, profile)
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response = self.llm_client.chat(messages)
            interpretation: SchemaInterpretation = self.parser.parse(response.content)
            return interpretation.fields
        except Exception as exc:  # noqa: BLE001 - any LLM failure must fall back
            logger.warning("LLM schema interpretation failed, falling back: %s", exc)
            # Lazy import breaks the circular dependency: schema imports this
            # module lazily, and we import schema lazily here.
            from opti_mind.data.schema import HeuristicSchemaInterpreter

            return HeuristicSchemaInterpreter().interpret(columns, profile)

    def propose_mapping(
        self,
        columns: list[str],
        profile: DataProfileReport,
        sample_rows: list[dict[str, Any]],
        problem_type_hint: str | None = None,
    ) -> SchemaMappingProposal:
        """Generate a full mapping proposal from column names, profile, and samples.

        Falls back to a heuristic proposal if the LLM call or parsing fails.
        """
        try:
            prompt = self._build_proposal_prompt(columns, profile, sample_rows, problem_type_hint)
            messages = [
                {"role": "system", "content": _MAPPING_PROPOSAL_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response = self.llm_client.chat(messages)
            parsed = self.proposal_parser.parse(response.content)
            self._normalize_symbols(parsed, problem_type_hint)
            return SchemaMappingProposal(
                problem_type=parsed.problem_type,
                fields=parsed.fields,
                overall_reasoning=parsed.overall_reasoning,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM mapping proposal failed, falling back: %s", exc)
            return self._heuristic_mapping_proposal(columns, profile, problem_type_hint)
        """Map columns to optimization semantics using the LLM.

        Falls back to the heuristic interpreter if the LLM call or output
        parsing fails, so the pipeline is never blocked by an LLM outage.

        Args:
            columns: List of column names from the dataset.
            profile: Statistical profile produced by DataProfiler.

        Returns:
            A list of FieldSemantics, one per input column.
        """
        try:
            prompt = self._build_prompt(columns, profile)
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response = self.llm_client.chat(messages)
            interpretation: SchemaInterpretation = self.parser.parse(response.content)
            return interpretation.fields
        except Exception as exc:  # noqa: BLE001 - any LLM failure must fall back
            logger.warning("LLM schema interpretation failed, falling back: %s", exc)
            # Lazy import breaks the circular dependency: schema imports this
            # module lazily, and we import schema lazily here.
            from opti_mind.data.schema import HeuristicSchemaInterpreter

            return HeuristicSchemaInterpreter().interpret(columns, profile)

    def check_clarification(
        self,
        columns: list[str],
        semantics: list[FieldSemantics],
        problem_type: str | None = None,
        resolved_parameters: dict[str, Any] | None = None,
    ) -> ClarificationRequest | None:
        """Inspect semantics and raise a ClarificationRequest if a critical
        role is missing or any mapped field has low confidence.

        If ``problem_type`` is provided, the check is driven by the ontology's
        parameter list so that missing parameters can be asked for by their
        canonical symbol (e.g. ``d_i``). Otherwise a generic set of critical
        roles is used.

        Returns None when semantics look usable as-is.
        """
        roles = {s.semantic_role for s in semantics if s.semantic_role}
        symbols = {s.optimization_symbol for s in semantics if s.optimization_symbol}

        # Problem-type-aware missing-parameter check.
        if problem_type:
            try:
                entry = OntologyRepository().get(ProblemType(problem_type))
                canonical_roles = {s.canonical_role for s in semantics if s.canonical_role}
                role_map = _PARAM_ROLE_MAP.get(problem_type, {})
                auto_computed = set(entry.signature.get("auto_computed_parameters", []))
                missing = [
                    param_symbol
                    for param_symbol in entry.parameters
                    if param_symbol not in symbols
                    and role_map.get(param_symbol) not in canonical_roles
                    and param_symbol not in auto_computed
                ]
                if missing:
                    param_symbol = missing[0]
                    target_role = _SYMBOL_ROLE_HINTS.get(param_symbol, param_symbol.split("_")[0])
                    candidates = self._candidate_columns_for_role(columns, semantics, target_role)
                    options = [ClarificationOption(label=c, value=c) for c in candidates]
                    recognized = self._recognized_fields_text(semantics)
                    question = CHAT_STRINGS.format_data_intelligence_question(
                        role_name=target_role,
                        symbol=param_symbol,
                        options_text=", ".join(candidates) if candidates else "",
                        recognized_text=recognized,
                    )
                    return ClarificationRequest(
                        station="data_intelligence",
                        question=question,
                        options=options,
                        expected_field=param_symbol,
                        context={
                            "missing_role": target_role,
                            "target_role": target_role,
                            "target_symbol": param_symbol,
                            "problem_type": problem_type,
                            "recognized_fields": recognized,
                        },
                    )
                # All ontology parameters are present: do not fall through to
                # generic critical-role checks that may ask for unrelated roles.
                return None
            except Exception:  # noqa: BLE001 - ontology lookup is advisory
                pass

        # Generic critical-role fallback.
        canonical_roles = {s.canonical_role for s in semantics if s.canonical_role}
        for role, canonical in _CRITICAL_ROLES.items():
            if role not in roles and canonical not in canonical_roles:
                target_symbol = _ROLE_SYMBOL_HINTS.get(role, "")
                candidates = self._candidate_columns_for_role(columns, semantics, role)
                recognized = self._recognized_fields_text(semantics)
                question = CHAT_STRINGS.format_data_intelligence_question(
                    role_name=role,
                    symbol=target_symbol,
                    options_text=", ".join(candidates) if candidates else "",
                    recognized_text=recognized,
                )
                return ClarificationRequest(
                    station="data_intelligence",
                    question=question,
                    options=[ClarificationOption(label=c, value=c) for c in candidates],
                    expected_field=role,
                    context={
                        "missing_role": role,
                        "target_role": role,
                        "target_symbol": target_symbol,
                        "recognized_fields": recognized,
                    },
                )

        low = [
            s for s in semantics if s.optimization_symbol and s.confidence < _CONFIDENCE_THRESHOLD
        ]
        if low:
            sem = low[0]
            sym = sem.optimization_symbol or sem.semantic_role or sem.column
            return ClarificationRequest(
                station="data_intelligence",
                question=(
                    f"The mapping for column '{sem.column}' -> {sym} "
                    "has low confidence. Is this correct?"
                ),
                options=[ClarificationOption(label=str(c), value=str(c)) for c in columns],
                expected_field=sym,
                context={
                    "column": sem.column,
                    "confidence": str(sem.confidence),
                    "target_role": sem.semantic_role or "",
                    "target_symbol": sem.optimization_symbol or "",
                },
            )

        return None

    def _candidate_columns_for_role(
        self,
        columns: list[str],
        semantics: list[FieldSemantics],
        target_role: str,
    ) -> list[str]:
        """Return columns that might satisfy the given canonical role.

        Columns already mapped to a different semantic role or symbol are
        excluded so the user does not see obviously wrong choices.
        """
        # Gather columns already consumed by another role/symbol.
        consumed: set[str] = set()
        for sem in semantics:
            col = sem.column
            has_mapping = sem.semantic_role or sem.optimization_symbol
            mapped_to_other = (
                sem.semantic_role != target_role
                and getattr(sem.canonical_role, "value", None) != target_role
            )
            if col and has_mapping and mapped_to_other:
                consumed.add(col)

        # Prefer columns that match the role by name (keyword_mapping).
        candidates: list[str] = []
        for col in columns:
            if col in consumed:
                continue
            key = str(col).lower().strip()
            if is_index_keyword(key):
                # Index columns identify sets; they are unlikely to be parameters.
                continue
            canonical = get_canonical_role(key)
            if canonical is not None and canonical.value == target_role:
                candidates.append(col)
                continue
            role, symbol = get_semantic_role_and_symbol(key)
            if role == target_role:
                candidates.append(col)

        if candidates:
            return candidates

        # Fallback: any non-index, non-consumed column (free-text mode will
        # still be allowed because options is not empty, but we at least strip
        # the obviously wrong ones).
        return [
            col
            for col in columns
            if col not in consumed and not is_index_keyword(str(col).lower().strip())
        ]

    @staticmethod
    def _recognized_fields_text(semantics: list[FieldSemantics]) -> str:
        """Return a human-readable summary of already-mapped columns."""
        lines: list[str] = []
        for sem in semantics:
            role = sem.semantic_role or (sem.canonical_role.value if sem.canonical_role else None)
            symbol = sem.optimization_symbol
            if not role and not symbol:
                continue
            parts: list[str] = []
            if role:
                parts.append(role)
            if symbol:
                parts.append(symbol)
            lines.append(f"- `{sem.column}` -> {': '.join(parts)}")
        return "\n".join(lines) if lines else "（暂无）"

    def _build_prompt(self, columns: list[str], profile: DataProfileReport) -> str:
        """Build the human prompt for the LLM."""
        profile_text = "\n".join(
            f"- {col.name}: dtype={col.dtype}, missing={col.missing_rate:.2%}, "
            f"unique={col.unique_count}, min={col.min_value}, max={col.max_value}"
            for col in profile.columns
        )
        return (
            f"Columns: {json.dumps(columns)}\n\n"
            f"Profile:\n{profile_text}\n\n"
            f"{self.format_instructions}"
        )

    def _build_proposal_prompt(
        self,
        columns: list[str],
        profile: DataProfileReport,
        sample_rows: list[dict[str, Any]],
        problem_type_hint: str | None,
    ) -> str:
        """Build the prompt for the full mapping proposal."""
        profile_text = "\n".join(
            f"- {col.name}: dtype={col.dtype}, missing={col.missing_rate:.2%}, "
            f"unique={col.unique_count}, min={col.min_value}, max={col.max_value}"
            for col in profile.columns
        )
        parts = [
            f"Columns: {json.dumps(columns, ensure_ascii=False)}",
            f"Profile:\n{profile_text}",
            f"Sample rows:\n{json.dumps(sample_rows, ensure_ascii=False, indent=2)}",
        ]
        if problem_type_hint:
            parts.append(f"Problem type hint: {problem_type_hint}")
        parts.append(self.proposal_format_instructions)
        return "\n\n".join(parts)

    def _normalize_symbols(
        self,
        proposal: _MappingProposalOutput,
        problem_type_hint: str | None,
    ) -> None:
        """Force each field's optimization_symbol to the ontology canonical symbol.

        This prevents the LLM from displaying invented notation such as K_i or
        I_i^0, which confuses downstream parameter collection.
        """
        problem_type = problem_type_hint or proposal.problem_type
        if not problem_type:
            return
        for field in proposal.fields:
            if not field.canonical_role:
                continue
            canonical = _CANONICAL_SYMBOLS.get((problem_type, field.canonical_role.value))
            if canonical:
                field.optimization_symbol = canonical

    def _heuristic_mapping_proposal(
        self,
        columns: list[str],
        profile: DataProfileReport,
        problem_type_hint: str | None,
    ) -> SchemaMappingProposal:
        """Build a fallback proposal from the heuristic interpreter."""
        from opti_mind.data.schema import HeuristicSchemaInterpreter

        semantics = HeuristicSchemaInterpreter().interpret(columns, profile)
        fields = [
            FieldMappingProposal(
                column=sem.column,
                semantic_role=sem.semantic_role,
                optimization_symbol=sem.optimization_symbol,
                canonical_role=sem.canonical_role,
                confidence=sem.confidence,
                chinese_label=CHAT_STRINGS._role_display_name(
                    sem.canonical_role.value if sem.canonical_role else (sem.semantic_role or "")
                ),
                reasoning="",
                is_index=sem.is_index,
            )
            for sem in semantics
        ]
        return SchemaMappingProposal(
            problem_type=problem_type_hint,
            fields=fields,
            overall_reasoning="基于关键词规则的初步映射，请确认或修改。",
        )

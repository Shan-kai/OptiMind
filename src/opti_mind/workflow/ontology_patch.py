"""Ontology patch node: apply deterministic completions or request LLM patch.

This node consumes a :class:`~opti_mind.ontology.gap_report.GapReport` from
state and decides whether to:

1. Apply a deterministic completion (keyword/alias/default).
2. Call :meth:`IOntologyService.patch_for` for an LLM-driven ontology patch.
3. Auto-apply the patch (confidence >= 0.9, or 0.7 ~ 0.9 with summary).
4. Raise a clarification when confidence < 0.7 or the patch is high-risk.
5. Abort after ``upstream_attempts`` reaches 2.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from langgraph.types import interrupt

from opti_mind.chat.i18n import CHAT_STRINGS
from opti_mind.data.models import OptimizationInstance
from opti_mind.ontology.gap_report import GapKind, GapReport
from opti_mind.ontology.service import (
    OntologyPatch,
    OntologyServiceConfig,
    ParameterPatch,
    compute_patch_approval,
    shape_default,
)
from opti_mind.workflow.clarification import (
    ClarificationOption,
    ClarificationRequest,
    ClarificationResponse,
)
from opti_mind.workflow.context import WorkflowDependencies

logger = logging.getLogger(__name__)

MAX_UPSTREAM_ATTEMPTS = OntologyServiceConfig().max_upstream_attempts


def run_ontology_patch(
    state: Mapping[str, Any],
    deps: WorkflowDependencies,
) -> dict[str, Any]:
    """Run the ontology patch node.

    Returns a state update dict. When a clarification is required, the node
    raises it via ``interrupt`` and does not return until the user resumes.
    """
    gap_data = state.get("gap_report")
    if not gap_data:
        return {"errors": ["ontology_patch: missing gap_report in state"]}

    gap = GapReport.model_validate(gap_data)

    if gap.upstream_attempts >= MAX_UPSTREAM_ATTEMPTS:
        return {
            "errors": [
                "ontology_patch_exhausted: reached maximum retry attempts. "
                f"Last gap: {gap.gap_kind} at {gap.trigger_station}."
            ],
            "gap_report": None,
        }

    # Resume path: a modeling-style answer may have been returned from a manual
    # input request. Forward it to the modeling node instead of re-processing.
    clarification_response = state.get("clarification_response")
    if clarification_response is not None:
        resp = ClarificationResponse.model_validate(clarification_response)
        if resp.station == "modeling":
            return {
                "gap_report": None,
                "next_node": "modeling",
                "clarification_response": resp.model_dump(mode="json"),
            }

    # First, try deterministic completion using ontology defaults/aliases.
    state_dict = dict(state)
    deterministic_result = _try_deterministic_completion(state_dict, gap, deps)
    if deterministic_result:
        return deterministic_result

    # Deterministic path failed: ask OntologyService for an LLM patch.
    patch = deps.ontology_service.patch_for(
        gap,
        instance=state_dict.get("instance"),
        field_semantics=state_dict.get("field_semantics"),
        business_goal=state_dict.get("business_goal") or "",
    )

    # No concrete patch available: ask the user for a modeling-style parameter
    # value directly, bypassing the empty ontology patch approval step.
    if not patch.parameter_patches and gap.missing_parameters:
        expected_field = gap.missing_parameters[0]
        req = _build_modeling_clarification_from_gap(gap, expected_field)
        answer = interrupt(req)
        resp = ClarificationResponse.model_validate(answer)
        return {
            "gap_report": None,
            "next_node": "modeling",
            "clarification_response": resp.model_dump(mode="json"),
        }

    return _apply_or_request_patch(state_dict, gap, patch, deps)


def _try_deterministic_completion(
    state: Mapping[str, Any],
    gap: GapReport,
    deps: WorkflowDependencies,
) -> dict[str, Any] | None:
    """Try to close the gap without calling the LLM.

    Currently supports parameter completion from ontology defaults. Returns a
    state update that routes back to the upstream node, or ``None`` if no
    deterministic completion is possible.
    """
    if gap.gap_kind != GapKind.REQUIRED_PARAMETERS_MISSING or not gap.missing_parameters:
        return None

    problem_type = gap.detected_problem_type or state.get("problem_type")
    if not problem_type:
        return None

    entry = deps.ontology_service.get_entry(problem_type)
    if entry is None:
        return None

    instance_data = state.get("instance")
    if not isinstance(instance_data, dict):
        return None

    instance = OptimizationInstance.model_validate(instance_data)
    applied: list[ParameterPatch] = []

    for symbol in gap.missing_parameters:
        base = symbol.split("_", 1)[0] if "_" in symbol else symbol
        if base not in entry.defaults:
            continue
        value = shape_default(symbol, instance, entry.defaults[base])
        instance.parameters[symbol] = value
        applied.append(
            ParameterPatch(
                symbol=symbol,
                value=value,
                reason=f"Filled from ontology default for '{base}'",
            )
        )

    if not applied:
        return None

    assumptions = [f"{p.symbol}: {p.reason}" for p in applied]
    return {
        "instance": instance.model_dump(mode="json"),
        "assumptions": list(state.get("assumptions") or []) + assumptions,
        "gap_report": None,
        "next_node": _upstream_node(gap.trigger_station),
    }


def _apply_or_request_patch(
    state: Mapping[str, Any],
    gap: GapReport,
    patch: OntologyPatch,
    deps: WorkflowDependencies,
) -> dict[str, Any]:
    """Route patch based on confidence and risk."""
    cfg = OntologyServiceConfig()
    approval = compute_patch_approval(patch.confidence, cfg)

    # Low confidence / high risk requires human approval.
    if approval["requires_approval"] or _is_high_risk_patch(patch):
        req = _build_ontology_patch_clarification(patch, gap)
        answer = interrupt(req)
        return _handle_patch_clarification_answer(state, gap, patch, answer, deps)

    # Medium confidence: auto-apply but surface a summary.
    if approval["show_summary"]:
        summary = _patch_summary(patch)
        logger.info(
            "Auto-applying ontology patch with confidence %.2f: %s",
            patch.confidence,
            summary,
        )

    return _apply_patch(state, gap, patch, deps)


def _is_high_risk_patch(patch: OntologyPatch) -> bool:
    """Return True if the patch changes problem type or objective/constraint semantics."""
    return (
        patch.problem_type_suggestion is not None
        or bool(patch.ontology_extensions)
        or bool(patch.role_mappings or patch.set_patches)
    )


def _build_ontology_patch_clarification(
    patch: OntologyPatch,
    gap: GapReport,
) -> ClarificationRequest:
    """Build a ClarificationRequest for ontology patch approval."""
    summary = _patch_summary(patch)
    question = CHAT_STRINGS.format_ontology_patch_question(summary, patch.confidence)
    missing_symbols = [p.symbol for p in patch.parameter_patches] or gap.missing_parameters

    options: list[ClarificationOption] = []
    if patch.parameter_patches:
        options = [
            ClarificationOption(label="同意并应用", value="approve"),
            ClarificationOption(label="拒绝并手动输入", value="reject"),
        ]
    else:
        options = [ClarificationOption(label="手动输入", value="manual")]

    return ClarificationRequest(
        station="ontology_patch",
        question=question,
        options=options,
        expected_field="ontology_patch_decision",
        context={
            "patch": patch.model_dump_json(),
            "confidence": str(patch.confidence),
            "gap_kind": gap.gap_kind,
            "trigger_station": gap.trigger_station,
            "missing_parameters": ",".join(missing_symbols),
        },
    )


def _patch_summary(patch: OntologyPatch) -> str:
    """Return a human-readable summary of the patch."""
    lines: list[str] = []
    if patch.role_mappings:
        lines.append(f"角色映射：{len(patch.role_mappings)} 项")
    if patch.parameter_patches:
        symbols = ", ".join(p.symbol for p in patch.parameter_patches)
        lines.append(f"参数补全：{symbols}")
    if patch.set_patches:
        lines.append(f"集合推断：{len(patch.set_patches)} 项")
    if patch.reasoning:
        lines.append(f"说明：{'; '.join(patch.reasoning)}")
    return "\n".join(lines) if lines else "（无详情）"


def _handle_patch_clarification_answer(
    state: Mapping[str, Any],
    gap: GapReport,
    patch: OntologyPatch,
    answer: Any,
    deps: WorkflowDependencies,
) -> dict[str, Any]:
    """Apply approved parts of a patch after user clarification."""
    from opti_mind.workflow.clarification import ClarificationResponse

    resp = ClarificationResponse.model_validate(answer)
    decision = (resp.answer or "").strip().lower()
    if decision in ("approve", "同意", "同意并应用"):
        return _apply_patch(state, gap, patch, deps)

    if decision in ("manual", "手动输入", "手动"):
        # User wants to enter the value directly; keep the gap alive but signal
        # the chat layer to switch to a modeling-style parameter input.
        expected_field = gap.missing_parameters[0] if gap.missing_parameters else ""
        return {
            "errors": [
                f"ontology_patch at {gap.trigger_station} requires manual input for: "
                f"{', '.join(gap.missing_parameters)}."
            ],
            "next_clarification_station": "modeling",
            "next_clarification_expected_field": expected_field,
            "gap_report": gap.bump_attempt().model_dump(mode="json"),
        }

    # Rejected: keep the gap but bump attempts so the loop can terminate.
    return {
        "errors": [
            f"ontology_patch rejected by user at {gap.trigger_station}. "
            "Please provide missing data or adjust the problem type."
        ],
        "gap_report": gap.bump_attempt().model_dump(mode="json"),
    }


def _apply_patch(
    state: Mapping[str, Any],
    gap: GapReport,
    patch: OntologyPatch,
    deps: WorkflowDependencies,
) -> dict[str, Any]:
    """Apply a patch to state and route back to the upstream node."""
    instance_data = state.get("instance")
    if isinstance(instance_data, dict):
        result = deps.ontology_service.apply_patch(patch, instance_data)
        if result.success and result.updated_instance is not None:
            instance_data = result.updated_instance.model_dump(mode="json")
        elif result.errors:
            return {
                "errors": [f"ontology_patch apply failed: {e}" for e in result.errors],
                "gap_report": gap.bump_attempt().model_dump(mode="json"),
            }

    assumptions = list(state.get("assumptions") or [])
    assumptions.extend(patch.reasoning)
    for a in patch.parameter_patches:
        if a.reason:
            assumptions.append(f"{a.symbol}: {a.reason}")

    return {
        "instance": instance_data,
        "assumptions": assumptions,
        "gap_report": None,
        "next_node": _upstream_node(gap.trigger_station),
    }


def _upstream_node(trigger_station: str) -> str:
    """Map the trigger station to the node we should return to."""
    if trigger_station == "data_intelligence":
        return "data_intelligence"
    if trigger_station == "verification":
        return "modeling"
    return "modeling"


def _build_modeling_clarification_from_gap(
    gap: GapReport, expected_field: str
) -> ClarificationRequest:
    """Build a modeling-style clarification for a missing parameter."""
    return ClarificationRequest(
        station="modeling",
        question=f"请提供缺失参数 {expected_field} 的值。",
        options=[],
        expected_field=expected_field,
        context={
            "missing_parameters": ",".join(gap.missing_parameters),
            "problem_type": gap.detected_problem_type or "",
            "example_answer": "0.0",
        },
    )

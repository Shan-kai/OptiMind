"""Gap detection: A/B/C/D four-stage composite gate.

Produces a structured :class:`~opti_mind.ontology.gap_report.GapReport` that
tells the workflow whether the deterministic path can proceed, needs
ontology patching, or should ask the user for clarification.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from opti_mind.ontology.gap_report import GapKind, GapReport


def detect_gap(state: Mapping[str, Any], confidence_threshold: float = 0.4) -> GapReport | None:
    """Inspect workflow state and return a GapReport if a gap is found.

    The trigger station is inferred from the outputs already present in state:

    - ``data_intelligence``: instance exists but knowledge_package does not.
    - ``modeling``: ir exists but verification_report does not.
    - ``verification``: verification_report exists.

    Returns ``None`` when no gap is detected (deterministic path may proceed).
    """
    instance = state.get("instance")
    knowledge_package = state.get("knowledge_package")
    ir = state.get("ir")
    verification_report = state.get("verification_report")
    problem_type = state.get("problem_type")

    if instance is not None and knowledge_package is None:
        return _detect_data_intelligence_gap(dict(state), problem_type, confidence_threshold)

    if ir is not None and verification_report is None:
        return _detect_modeling_gap(dict(state), problem_type)

    if verification_report is not None:
        return _detect_verification_gap(dict(state), problem_type, verification_report)

    return None


def _detect_data_intelligence_gap(
    state: Mapping[str, Any],
    problem_type: str | None,
    confidence_threshold: float,
) -> GapReport | None:
    """Stage A/B: problem-type uncertain or required schema roles missing."""
    pt_match = state.get("problem_type_match")
    confidence = 1.0
    candidates: list[str] = []
    if isinstance(pt_match, dict):
        confidence = float(pt_match.get("confidence", 1.0))
        candidates = [str(c) for c in pt_match.get("candidates", [])]

    if confidence < confidence_threshold:
        return GapReport(
            trigger_station="data_intelligence",
            gap_kind=GapKind.PROBLEM_TYPE_UNCERTAIN,
            confidence=confidence,
            detected_problem_type=problem_type,
            problem_type_candidates=candidates,
            recommended_patch_kind="problem_type_clarify",
        )

    instance = state.get("instance")
    if not isinstance(instance, dict):
        return None

    missing_roles = instance.get("meta", {}).get("missing_roles") or []
    if missing_roles:
        return GapReport(
            trigger_station="data_intelligence",
            gap_kind=GapKind.REQUIRED_ROLES_MISSING,
            confidence=confidence,
            detected_problem_type=problem_type,
            missing_roles=[str(r) for r in missing_roles],
            recommended_patch_kind="schema_remap",
        )

    return None


def _detect_modeling_gap(state: Mapping[str, Any], problem_type: str | None) -> GapReport | None:
    """Stage C: required parameters missing after deterministic IR generation."""
    missing = state.get("missing_parameters") or []
    if not missing:
        return None

    # Confidence inversely proportional to the share of required parameters
    # that are missing. A single missing parameter out of many is less severe
    # than most parameters missing.
    total_required = max(len(missing) + len(state.get("inferred_parameters") or []), len(missing))
    confidence = round(1.0 - (len(missing) / max(total_required, 1)), 3)

    return GapReport(
        trigger_station="modeling",
        gap_kind=GapKind.REQUIRED_PARAMETERS_MISSING,
        confidence=confidence,
        detected_problem_type=problem_type,
        missing_parameters=[str(m) for m in missing],
        recommended_patch_kind="parameter_completion",
    )


def _detect_verification_gap(
    state: Mapping[str, Any],
    problem_type: str | None,
    verification_report: dict[str, Any],
) -> GapReport | None:
    """Stage D: IR validation failed for ontology/semantic reasons."""
    passed = verification_report.get("passed")
    if passed is None:
        results = verification_report.get("results") or []
        passed = all(isinstance(r, dict) and r.get("passed") for r in results)
    if passed:
        return None

    failures = verification_report.get("failures") or []
    if not failures:
        results = verification_report.get("results") or []
        failures = [r for r in results if isinstance(r, dict) and not r.get("passed")]

    failure_texts = [
        f"{f.get('check_name', 'check')}: {f.get('details', '')}" if isinstance(f, dict) else str(f)
        for f in failures
    ]

    # Confidence falls with failure severity/count. One failure leaves some
    # trust in the deterministic path; many failures mean ontology patching is
    # the only safe option.
    error_count = sum(
        1
        for f in failures
        if isinstance(f, dict) and (f.get("severity") == "error" or not f.get("passed", True))
    )
    total = max(len(failures), 1)
    confidence = round(1.0 - (error_count / total) * 0.5, 3)

    return GapReport(
        trigger_station="verification",
        gap_kind=GapKind.IR_VALIDATION_FAILED,
        confidence=confidence,
        detected_problem_type=problem_type,
        validation_failures=failure_texts,
        recommended_patch_kind="ontology_extension",
    )

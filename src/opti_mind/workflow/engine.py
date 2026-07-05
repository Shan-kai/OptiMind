"""LangGraph workflow engine. Default pipeline with a real Data Intelligence node."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from functools import partial, wraps
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from opti_mind.config import get_settings
from opti_mind.data.models import FieldSemantics, OptimizationInstance
from opti_mind.knowledge.models import KnowledgePackage, ProblemSpecification
from opti_mind.ontology.models import ProblemType
from opti_mind.ontology.service import OntologyService
from opti_mind.workflow.clarification import ClarificationRequest, ClarificationResponse
from opti_mind.workflow.context import WorkflowDependencies, default_workflow_dependencies
from opti_mind.workflow.gap_detection import detect_gap
from opti_mind.workflow.ontology_patch import run_ontology_patch
from opti_mind.workflow.state import WorkflowState

logger = logging.getLogger(__name__)


def _observe_node(func: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """为工作流节点添加开始/结束/耗时/错误日志，不修改异常传播行为。"""

    @wraps(func)
    def wrapper(state: WorkflowState, *args: Any, **kwargs: Any) -> dict[str, Any]:
        node_name = func.__name__.removeprefix("_").removesuffix("_node")
        logger.info("%s node started", node_name)
        start = time.perf_counter()
        try:
            result = func(state, *args, **kwargs)
        finally:
            duration = time.perf_counter() - start
            logger.info("%s node completed in %.3fs", node_name, duration)

        if isinstance(result, dict):
            errors = result.get("errors", [])
            if errors:
                logger.error("%s node errors: %s", node_name, errors)
        return result

    return wrapper


def _apply_data_clarification(
    semantics: list[FieldSemantics],
    response: ClarificationResponse,
) -> list[FieldSemantics]:
    """Patch the schema semantics using a user's clarification answer.

    The response is expected to carry ``target_role`` and ``target_symbol``
    in its context (for data_intelligence requests). If the answered column
    already exists in semantics, its role/symbol/confidence are updated;
    otherwise a new FieldSemantics entry is appended.

    Special answers:
    - ``__missing__`` means the user does not have this column. The semantics
      are left unchanged so downstream gap detection can offer defaults/manual
      input.
    """
    context = response.context or {}
    target_role = context.get("target_role") or response.expected_field
    target_symbol = context.get("target_symbol") or response.expected_field
    answer = response.answer.strip()

    if answer == "__missing__":
        return semantics

    for sem in semantics:
        if sem.column == answer:
            sem.semantic_role = target_role
            sem.optimization_symbol = target_symbol
            sem.confidence = 1.0
            return semantics

    semantics.append(
        FieldSemantics(
            column=answer,
            semantic_role=target_role,
            optimization_symbol=target_symbol,
            confidence=1.0,
        )
    )
    return semantics


@_observe_node
def _data_intelligence_node(state: WorkflowState, deps: WorkflowDependencies) -> dict[str, Any]:
    """Ingest raw data and build an Optimization Instance."""
    source = state.get("source") or state.get("dataset_id")
    if not source:
        return {"errors": ["data_intelligence: missing source"]}

    df = deps.data_service.load_df(str(source))
    columns = list(df.columns)
    profile = deps.data_service.profiler.profile(df)
    semantics = deps.data_service.schema_interpreter.interpret(columns, profile)

    # If a clarification response is present, apply it and rebuild.
    clarification_response = state.get("clarification_response")
    if clarification_response is not None:
        resp = ClarificationResponse.model_validate(clarification_response)
        if resp.station == "data_intelligence":
            semantics = _apply_data_clarification(semantics, resp)
        # Clear the response so it is not re-applied on the next node re-entry.
        state["clarification_response"] = None

    instance = deps.data_service.rebuild_instance(
        df,
        semantics,
        dataset_id=Path(str(source)).stem,
        problem_type=state.get("problem_type"),
    )

    # Preserve parameters manually provided by the user across pipeline re-runs.
    # The CSV may not contain these columns, so the rebuilt instance would lose them.
    old_instance_data = state.get("instance")
    if old_instance_data:
        try:
            old_instance = OptimizationInstance.model_validate(old_instance_data)
            for key, value in old_instance.parameters.items():
                if key not in instance.parameters:
                    instance.parameters[key] = value
        except Exception:  # noqa: BLE001
            pass

    # Attach ontology entry metadata so downstream modeling tools can resolve aliases.
    effective_problem_type = state.get("problem_type") or instance.problem_type
    try:
        entry = deps.ontology_service.get_entry(effective_problem_type)
        if entry is not None:
            instance.meta["ontology_entry"] = entry.model_dump(mode="json")
    except Exception:  # noqa: BLE001
        pass

    # Use ontology service to detect problem type and surface confidence.
    detection = deps.ontology_service.detect(
        columns=columns,
        semantics=semantics,
        hint=state.get("problem_type"),
    )
    problem_type_match = detection.model_dump(mode="json")

    # Check if the schema interpreter (when LLM-backed) wants clarification.
    schema_interp = deps.data_service.schema_interpreter
    if hasattr(schema_interp, "check_clarification"):
        req = schema_interp.check_clarification(
            columns,
            semantics,
            problem_type=effective_problem_type,
            resolved_parameters=instance.parameters,
        )
        # Auto-computed parameters (e.g. inventory big-M) should never block the
        # pipeline, even if the LLM mapped them as missing.
        if req is not None:
            try:
                entry = deps.ontology_service.get_entry(effective_problem_type)
                if entry is not None:
                    auto_computed = set(entry.signature.get("auto_computed_parameters", []))
                    if req.expected_field in auto_computed:
                        req = None
            except Exception:  # noqa: BLE001
                pass
        if req is not None:
            # If the user has already confirmed this role is missing (e.g. by
            # providing c_ij as a parameter value), skip the interrupt and let
            # the preserved parameter carry the pipeline forward.
            confirmed_missing = set(state.get("confirmed_missing_roles") or [])
            target_role = req.context.get("target_role") or req.context.get("missing_role") or ""
            if confirmed_missing and (
                req.expected_field in confirmed_missing or target_role in confirmed_missing
            ):
                logger.info(
                    "Skipping data_intelligence clarification for %s (confirmed missing)",
                    req.expected_field,
                )
            else:
                # Interrupt the graph and wait for human input.
                answer = interrupt(req)
                # When resumed, the interrupt returns the user's answer. Apply it
                # immediately so the next re-entry of this node starts patched.
                resp = ClarificationResponse.model_validate(answer)
                semantics = _apply_data_clarification(semantics, resp)
                instance = deps.data_service.rebuild_instance(
                    df,
                    semantics,
                    dataset_id=Path(str(source)).stem,
                    problem_type=effective_problem_type,
                )

    return {
        "dataset_id": instance.meta.get("dataset_id"),
        "problem_type": state.get("problem_type") or instance.problem_type,
        "instance": instance.model_dump(mode="json"),
        "field_semantics": [s.model_dump(mode="json") for s in semantics],
        "problem_type_match": problem_type_match,
        "errors": [],
        "clarification_response": None,
        "pending_clarification": None,
        "gap_report": None,
        "next_node": None,
    }


@_observe_node
def _knowledge_retrieval_node(state: WorkflowState, deps: WorkflowDependencies) -> dict[str, Any]:
    """Retrieve optimization knowledge based on problem type and instance."""
    problem_type = state.get("problem_type")
    instance = state.get("instance")
    if not problem_type:
        return {"errors": ["knowledge_retrieval: missing problem_type"]}
    try:
        pt_enum = ProblemType(problem_type)
    except ValueError:
        return {"errors": [f"knowledge_retrieval: unknown problem type {problem_type}"]}

    settings = get_settings()
    use_placeholder = settings.llm_model_generator and not state.get("use_ontology")
    if use_placeholder:
        # Deprecated placeholder kept for backwards compatibility. The
        # ontology-driven path is now the only supported modeling path.
        entry = deps.ontology_service.get_entry(pt_enum.value)
        if entry is None:
            return {"errors": [f"knowledge_retrieval: ontology entry not found for {problem_type}"]}
        package = KnowledgePackage(
            problem_type=pt_enum,
            ontology_entry=entry,
            variables=list(entry.variables),
            constraints=list(entry.constraints),
            objective=entry.objective,
            notes=["ontology-driven knowledge retrieval"],
        )
        return {"knowledge_package": package.model_dump(mode="json"), "errors": []}

    available_fields = []
    if instance and isinstance(instance, dict):
        params = instance.get("parameters", {})
        available_fields = list(params.keys())
    spec = ProblemSpecification(problem_type=pt_enum, available_fields=available_fields)
    try:
        package = deps.ontology_service.retrieve(spec)
        return {"knowledge_package": package.model_dump(mode="json"), "errors": []}
    except Exception as e:
        return {"errors": [f"knowledge_retrieval: {str(e)}"]}


@_observe_node
def _gap_detection_node(state: WorkflowState, deps: WorkflowDependencies) -> dict[str, Any]:
    """Inspect workflow state and decide whether a gap needs patching."""
    del deps

    gap = detect_gap(dict(state))
    if gap is None:
        return {"gap_report": None}

    gap_data = gap.model_dump(mode="json")
    return {"gap_report": gap_data, "next_node": "ontology_patch"}


@_observe_node
def _ontology_patch_node(state: WorkflowState, deps: WorkflowDependencies) -> dict[str, Any]:
    """Apply deterministic completion or request an ontology patch."""
    return run_ontology_patch(dict(state), deps)


@_observe_node
def _decision_node(state: WorkflowState, deps: WorkflowDependencies) -> dict[str, Any]:
    """Run decision intelligence analysis on the solver solution."""
    solution = state.get("solution")
    ir_data = state.get("verified_ir") or state.get("ir")
    if not solution:
        return {"errors": ["decision: no solution to analyze"]}
    try:
        from opti_mind.modeling.ir_models import IRModel

        ir = IRModel.model_validate(ir_data) if ir_data else None
        report = deps.decision_service.analyze(
            solution,
            ir,
            scenarios=state.get("scenarios"),
            business_goal=state.get("business_goal"),
        )
        return {"report": report.model_dump(mode="json"), "errors": []}
    except Exception as e:
        return {"errors": [f"decision: {str(e)}"]}


@_observe_node
def _solver_node(state: WorkflowState, deps: WorkflowDependencies) -> dict[str, Any]:
    """Solve the verified IR using the configured solver backend.

    Preserves upstream errors, appends the solver-unavailability message when
    the router returns an ``error`` field, and keeps the solution in state so
    callers can inspect it.
    """
    ir_data = state.get("verified_ir") or state.get("ir")
    errors: list[str] = list(state.get("errors") or [])
    if not ir_data:
        errors.append("solver: no IR to solve")
        return {"errors": errors}
    try:
        result = deps.solver_router.solve_dict(dict(ir_data))
        error_message = result.get("error")
        if error_message:
            errors.append(f"solver: {error_message}")
        return {"solution": result, "errors": errors}
    except Exception as e:
        errors.append(f"solver: {str(e)}")
        return {"errors": errors}


def _apply_modeling_clarification(
    instance: OptimizationInstance,
    response: ClarificationResponse,
) -> OptimizationInstance:
    """Patch an OptimizationInstance using a user's modeling clarification.

    The answer is expected to be either a JSON-encoded value or the literal
    string "default". The expected_field should be the ontology parameter
    symbol (e.g. ``d_i``). The value is stored under the canonical symbol and
    the short base name.

    As a fallback for natural-language input, comma-separated numbers are
    mapped to the symbol's index sets in order.
    """
    symbol = response.expected_field
    answer = response.answer.strip()

    value: Any
    if answer.lower() in ("default", "use default"):
        value = _default_parameter_value(symbol, instance)
    else:
        try:
            parsed = json.loads(answer)
        except json.JSONDecodeError:
            parsed = _extract_numbers_from_text(answer)
        value = _shape_parameter_value(symbol, parsed, instance)

    instance.parameters[symbol] = value
    # Also populate the short base name when the ontology declares an alias for
    # this symbol, so the deterministic IR generator can resolve it from
    # ``instance.parameters``. Unknown symbols are kept under their canonical
    # name only.
    base = symbol.split("_", 1)[0] if "_" in symbol else symbol
    entry = instance.meta.get("ontology_entry")
    aliases: dict[str, list[str]] = {}
    if isinstance(entry, dict):
        aliases = entry.get("aliases") or {}
    if base != symbol and base in aliases:
        instance.parameters[base] = value
    return instance


def _extract_numbers_from_text(text: str) -> float | list[float] | str:
    """Extract numbers from text, supporting lists and row-major matrices.

    Supported separators: English/Chinese commas, spaces, semicolons.
    Semicolons are treated as row separators for matrix input; all numbers
    are flattened into a single row-major list.
    """
    # Normalize Chinese commas and whitespace to English commas, keep semicolons.
    normalized = text.replace("，", ",").replace(" ", ",").replace("　", ",")
    rows = [row.strip() for row in normalized.split(";") if row.strip()]
    all_numbers: list[float] = []
    for row in rows:
        parts = [p.strip() for p in row.split(",") if p.strip()]
        # Strip common labels like "c_1j:" from each part.
        cleaned: list[str] = []
        for part in parts:
            if ":" in part:
                part = part.split(":", 1)[1]
            cleaned.append(part.strip())
        for part in cleaned:
            try:
                all_numbers.append(float(part))
            except ValueError:
                continue
    if not all_numbers:
        try:
            return float(text)
        except ValueError:
            return text
    return all_numbers[0] if len(all_numbers) == 1 else all_numbers


def _shape_parameter_value(
    symbol: str,
    parsed: Any,
    instance: OptimizationInstance,
) -> Any:
    """Shape a parsed value (number or list) to the symbol's index structure."""
    if "_" not in symbol:
        if isinstance(parsed, list):
            return parsed[0] if parsed else 0.0
        return parsed

    index_sets = _parameter_index_sets(symbol, instance)
    if not index_sets:
        return parsed

    if isinstance(parsed, (int, float)):
        scalar = float(parsed)
        if len(index_sets) == 1:
            return {str(member): scalar for member in instance.sets[index_sets[0]]}
        return _nested_default(instance, index_sets, scalar)

    if isinstance(parsed, list):
        # Flatten nested lists so LLM-provided row-major matrices work
        # (e.g., [[1,2,3],[4,5,6],[7,8,9]]) as well as flat vectors.
        def _flatten_numbers(value: Any) -> list[float]:
            out: list[float] = []
            if isinstance(value, (list, tuple)):
                for item in value:
                    out.extend(_flatten_numbers(item))
            else:
                out.append(float(value))
            return out

        numbers = _flatten_numbers(parsed)
        if len(index_sets) == 1:
            members = instance.sets[index_sets[0]]
            return {
                str(member): numbers[i] if i < len(numbers) else numbers[-1]
                for i, member in enumerate(members)
            }
        # Multi-index: try to interpret as flattened row-major values.
        first, *rest = index_sets
        first_members = instance.sets[first]
        if len(rest) == 1:
            second_members = instance.sets[rest[0]]
            per_row = len(second_members)
            result: dict[str, Any] = {}
            for i, member in enumerate(first_members):
                start = i * per_row
                chunk = numbers[start : start + per_row]
                if not chunk:
                    chunk = [0.0] * per_row
                result[str(member)] = {
                    str(second_members[j]): chunk[j] if j < len(chunk) else chunk[-1]
                    for j in range(per_row)
                }
            return result
        return numbers

    return parsed


def _default_parameter_value(symbol: str, instance: OptimizationInstance) -> Any:
    """Return a safe default for a missing ontology parameter.

    The default is shaped by the uppercase index letters in the symbol's
    subscript (e.g. ``Q_j`` -> one-level dict over ``J``). Scalar defaults
    are ``0.0`` unless an ontology default is available.
    """
    base = symbol.split("_", 1)[0] if "_" in symbol else symbol
    scalar_default = instance.meta.get("ontology_defaults", {}).get(base, 0.0)

    if "_" not in symbol:
        return scalar_default

    index_sets = _parameter_index_sets(symbol, instance)
    if not index_sets:
        return scalar_default

    if len(index_sets) == 1:
        return {str(member): scalar_default for member in instance.sets[index_sets[0]]}

    return _nested_default(instance, index_sets, scalar_default)


def _nested_default(
    instance: OptimizationInstance,
    index_sets: list[str],
    scalar_default: float,
) -> dict[str, Any]:
    """Build a nested dict default for multi-index parameters."""
    first, *rest = index_sets
    result: dict[str, Any] = {}
    for member in instance.sets[first]:
        key = str(member)
        if rest:
            result[key] = _nested_default(instance, rest, scalar_default)
        else:
            result[key] = scalar_default
    return result


@_observe_node
def _modeling_node(state: WorkflowState, deps: WorkflowDependencies) -> dict[str, Any]:
    """Generate IR from the knowledge package and instance in state."""
    kp_data = state.get("knowledge_package")
    inst_data = state.get("instance")
    if not kp_data or not inst_data:
        return {"errors": ["modeling: missing knowledge_package or instance"]}

    instance = OptimizationInstance.model_validate(inst_data)

    # Apply any modeling clarification before generating.
    clarification_response = state.get("clarification_response")
    if clarification_response is not None:
        resp = ClarificationResponse.model_validate(clarification_response)
        if resp.station == "modeling":
            instance = _apply_modeling_clarification(instance, resp)
            state["clarification_response"] = None
            state["instance"] = instance.model_dump(mode="json")

    try:
        diagnostics = deps.ir_generator.generate_from_state_with_diagnostics(dict(state))
    except Exception as e:
        return {"errors": [f"modeling: {str(e)}"]}

    ir_model = diagnostics["ir"]
    return {
        "ir": ir_model.model_dump_safe(),
        "missing_parameters": diagnostics["missing_parameters"],
        "errors": [],
        "clarification_response": None,
        "pending_clarification": None,
        "gap_report": None,
        "next_node": None,
    }


def _build_modeling_clarification_request(
    missing: list[str],
    instance: OptimizationInstance,
    state: WorkflowState,
) -> ClarificationRequest:
    """Build a user-facing ClarificationRequest for the next missing parameter."""
    symbol = missing[0]
    shape_hint = _parameter_shape_hint(symbol, instance)
    example = _parameter_example(symbol, instance)
    return ClarificationRequest(
        station="modeling",
        question=(
            f"建模还需要参数 **{symbol}**，但当前数据源里没有提供。\n"
            f"请直接提供 `{symbol}` 的数值（格式：{example}），"
            "或者回复 `default` 使用系统建议值。"
        ),
        options=[],
        expected_field=symbol,
        context={
            "missing_parameters": ",".join(missing),
            "problem_type": state.get("problem_type") or "",
            "expected_shape": shape_hint,
            "example_answer": example,
        },
    )


def _parameter_index_sets(symbol: str, instance: OptimizationInstance) -> list[str]:
    """Extract the set names referenced by a parameter symbol's subscript.

    Subscripts in symbols like ``c_ij`` use lowercase letters; the matching
    instance set names are uppercase (``I``, ``J``).
    """
    if "_" not in symbol:
        return []
    subscript = symbol.split("_", 1)[1]
    return [ch.upper() for ch in subscript if ch.isalpha() and ch.upper() in instance.sets]


def _parameter_shape_hint(symbol: str, instance: OptimizationInstance) -> str:
    """Return a human-readable description of the expected value shape."""
    sets = _parameter_index_sets(symbol, instance)
    if not sets:
        return "a scalar number"
    if len(sets) == 1:
        return f"a dict mapping each member of set {sets[0]} to a number"
    return (
        f"a nested dict: for each member of set {sets[0]}, "
        f"a dict mapping members of set {sets[1]} to a number"
    )


def _parameter_example(symbol: str, instance: OptimizationInstance) -> str:
    """Return a JSON-shaped example for the expected answer."""
    sets = _parameter_index_sets(symbol, instance)
    if not sets:
        return "0.0"
    members = instance.sets[sets[0]]
    sample_key = str(members[0]) if members else "key"
    if len(sets) == 1:
        return json.dumps({sample_key: 0.0})
    nested_sets = sets[1:]
    nested_members = instance.sets[nested_sets[0]]
    nested_key = str(nested_members[0]) if nested_members else "key"
    return json.dumps({sample_key: {nested_key: 0.0}})


@_observe_node
def _verification_node(state: WorkflowState, deps: WorkflowDependencies) -> dict[str, Any]:
    """Validate the generated IR; only pass verified IR downstream."""
    ir_data = state.get("ir")
    if not ir_data:
        return {"errors": ["verification: missing ir in state"]}
    try:
        report = deps.model_validator.validate_dict(dict(ir_data))
        result: dict[str, Any] = {
            "verification_report": report.model_dump(mode="json"),
            "gap_report": None,
            "errors": [],
        }
        if report.passed:
            result["verified_ir"] = dict(ir_data)
        else:
            failures = "; ".join(f"{r.check_name}: {r.details}" for r in report.failures)
            result["errors"] = [f"verification failed: {failures}"]
        return result
    except Exception as e:
        return {"errors": [f"verification: {str(e)}"]}


def _route_after_modeling(state: WorkflowState) -> str:
    """Route after modeling based on gap detection result."""
    next_node = state.get("next_node")
    if next_node:
        return next_node
    if state.get("gap_report") is not None:
        return "ontology_patch"
    return "verification"


def _route_after_verification(state: WorkflowState) -> str:
    """Route after verification based on gap detection result."""
    next_node = state.get("next_node")
    if next_node:
        return next_node
    if state.get("gap_report") is not None:
        return "ontology_patch"
    return "solver"


def _route_after_data_intelligence(state: WorkflowState) -> str:
    """Route after data_intelligence based on gap detection result."""
    next_node = state.get("next_node")
    if next_node:
        return next_node
    if state.get("gap_report") is not None:
        return "ontology_patch"
    return "knowledge_retrieval"


def _route_after_ontology_patch(state: WorkflowState) -> str:
    """Route after ontology_patch based on the upstream trigger station."""
    gap_data = state.get("gap_report")
    if gap_data is not None:
        trigger = gap_data.get("trigger_station")
        if trigger == "data_intelligence":
            return "data_intelligence"
        return "modeling"

    # If no gap_report remains, we are coming back from a successful patch.
    # Go back to modeling so the normal modeling -> verification path can run.
    return "modeling"


def _route_after_gap_detection(state: WorkflowState) -> str:
    """Route after a generic gap detection node."""
    next_node = state.get("next_node")
    if next_node:
        return next_node
    if state.get("gap_report") is not None:
        return "ontology_patch"

    # Abort the pipeline when upstream errors exist and no usable outputs are
    # present yet. This prevents infinite loops when a node fails early.
    if state.get("errors") and state.get("verification_report") is None and state.get("ir") is None:
        return "__end__"

    # Infer the natural successor from the outputs present in state.
    if state.get("verification_report") is not None:
        return "solver"
    if state.get("ir") is not None:
        return "verification"
    if state.get("knowledge_package") is not None:
        return "modeling"
    return "knowledge_retrieval"


def build_optimization_graph(deps: WorkflowDependencies | None = None) -> Any:
    """Build the end-to-end optimization pipeline graph.

    Args:
        deps: Injectable dependency container. When ``None``, the default
            container is built via :func:`default_workflow_dependencies`.
    """
    deps = deps or default_workflow_dependencies()
    graph = StateGraph(WorkflowState)
    graph.add_node("data_intelligence", partial(_data_intelligence_node, deps=deps))
    graph.add_node("gap_detection", partial(_gap_detection_node, deps=deps))
    graph.add_node("knowledge_retrieval", partial(_knowledge_retrieval_node, deps=deps))
    graph.add_node("modeling", partial(_modeling_node, deps=deps))
    graph.add_node("ontology_patch", partial(_ontology_patch_node, deps=deps))
    graph.add_node("verification", partial(_verification_node, deps=deps))
    graph.add_node("solver", partial(_solver_node, deps=deps))
    graph.add_node("decision", partial(_decision_node, deps=deps))

    graph.set_entry_point("data_intelligence")
    graph.add_edge("data_intelligence", "gap_detection")
    graph.add_conditional_edges(
        "gap_detection",
        _route_after_gap_detection,
        {
            "ontology_patch": "ontology_patch",
            "knowledge_retrieval": "knowledge_retrieval",
            "modeling": "modeling",
            "verification": "verification",
            "solver": "solver",
            "__end__": END,
        },
    )
    graph.add_edge("knowledge_retrieval", "modeling")
    graph.add_edge("modeling", "gap_detection")
    graph.add_edge("verification", "gap_detection")
    graph.add_conditional_edges(
        "ontology_patch",
        _route_after_ontology_patch,
        {
            "data_intelligence": "data_intelligence",
            "modeling": "modeling",
        },
    )
    graph.add_edge("solver", "decision")
    graph.add_edge("decision", END)
    return graph.compile(checkpointer=deps.memory_saver)


# Backwards-compatible alias for code that imports the singleton directly.
_OntologyService = OntologyService

"""IR Generator: builds an IRModel from a KnowledgePackage + Instance.

This is the core of the Optimization Modeling layer. It takes the
retrieved ontology knowledge and the data instance, and compiles them
into a structured Intermediate Representation (IR) per IR_SPEC.
"""

from __future__ import annotations

import contextlib
import logging
import re
from typing import Any

from opti_mind.data.models import OptimizationInstance
from opti_mind.knowledge.models import KnowledgePackage
from opti_mind.modeling.ir_models import (
    SCHEMA_VERSION,
    IRConstraint,
    IRExpression,
    IRExpressionTerm,
    IRModel,
    IRParameter,
    IRSet,
    IRVariable,
)
from opti_mind.ontology.models import VariableKind

logger = logging.getLogger(__name__)


def _map_variable_kind(kind: VariableKind) -> str:
    """Map ontology VariableKind to IR domain string."""
    return {
        VariableKind.BINARY: "binary",
        VariableKind.INTEGER: "integer",
        VariableKind.CONTINUOUS: "continuous",
    }[kind]


def _expr_to_latex(expr: str) -> str:
    """Convert a symbolic expression string to a LaTeX math string."""
    if not expr:
        return ""

    latex = expr.strip()

    # Convert subscripts like c_ij, x_ij, f_j to c_{ij}, x_{ij}, f_{j}.
    latex = re.sub(r"\b([a-zA-Z])_([a-zA-Z0-9]+)\b", r"\1_{\2}", latex)

    # Convert sum_{...} to \sum_{...} and " in " inside indices to " \in ".
    def _sum_repl(match: re.Match[str]) -> str:
        idx = match.group(1)
        if " in " in idx:
            idx = idx.replace(" in ", r" \in ")
        return r"\sum_{" + idx + "}"

    latex = re.sub(r"sum_\{([^}]+)\}", _sum_repl, latex)

    # Convert forall / for all ... in ... quantifiers.
    latex = re.sub(
        r"(?:forall|for all)\s+([^,]+)\s+in\s+([^,]+)",
        lambda m: f"\\forall {m.group(1)} \\in {m.group(2)}",
        latex,
    )

    # Relational operators.
    latex = latex.replace("==", "=")
    latex = latex.replace("<=", r"\le")
    latex = latex.replace(">=", r"\ge")

    # Multiplication.
    latex = latex.replace("*", r" \cdot ")

    # Collapse multiple spaces.
    latex = re.sub(r"\s+", " ", latex).strip()
    return latex


def _constraint_to_latex(constraint: IRConstraint) -> str:
    """Build a full LaTeX string for a constraint."""
    scope = _expr_to_latex(constraint.scope) if constraint.scope else ""
    expr = _expr_to_latex(constraint.expr)
    rhs = _expr_to_latex(constraint.rhs) if constraint.rhs else ""
    sense_map = {"le": r"\le", "ge": r"\ge", "eq": "="}
    sense = sense_map.get(constraint.sense, constraint.sense)

    body = f"{expr} {sense} {rhs}".strip()
    if scope:
        return f"{scope}: {body}"
    return body


def _parse_objective_expression(expr: str) -> IRExpression:
    """Parse a symbolic objective expression into structured terms.

    Robustly handles various sum syntaxes:
        sum_{j in J} f_j * y_j
        sum_{(i,j) in A} c_ij * x_ij
        sum_{i in I} sum_{j in J} c_ij * x_ij

    Falls back to raw_expr when the expression is too complex to decompose.
    """
    expr = expr.strip()
    if not expr:
        return IRExpression(kind="linear")

    # Split into additive terms by '+' (naive; complex nested parens
    # are rare in objectives and the term is also kept in raw_expr).
    raw_terms = re.split(r"\s*\+\s*", expr)
    terms: list[IRExpressionTerm] = []

    for term_str in raw_terms:
        term_str = term_str.strip()

        # Greedily collect leading sum_{...} prefixes.
        sum_sets: list[str] = []
        rest = term_str
        while True:
            m = re.match(r"sum_\{([^}]+)\}\s*(.+)", rest)
            if not m:
                break
            # Extract set name: last token of "idx in SET" or "(i,j) in SET"
            set_token = m.group(1).strip()
            # Pull the set name: the part after the last "in"
            if " in " in set_token:
                sum_sets.append(set_token.split(" in ")[-1].strip())
            else:
                sum_sets.append(set_token)
            rest = m.group(2).strip()

        # Parse coef * var from the remainder.  Support multi-factor products such
        # as ``c_ij * d_i * x_ij`` by treating the last factor as the variable and
        # joining the preceding factors into the coefficient string.
        rest = rest.strip("()")
        factors = [f.strip() for f in re.split(r"\s*\*\s*", rest) if f.strip()]
        if len(factors) >= 2:
            coef, var = " * ".join(factors[:-1]), factors[-1]
        elif len(factors) == 1:
            coef, var = "1", factors[0]
        else:
            # Could not decompose this term; keep raw and skip terms.
            return IRExpression(kind="linear", raw_expr=expr, latex=_expr_to_latex(expr))

        terms.append(IRExpressionTerm(coef=coef, var=var, sum_sets=sum_sets, where=""))

    return IRExpression(kind="linear", terms=terms, raw_expr=expr, latex=_expr_to_latex(expr))


def _build_sets_from_instance(
    instance: OptimizationInstance,
    ontology_sets: dict[str, str],
) -> list[IRSet]:
    """Build IR sets from instance sets and ontology descriptions."""
    ir_sets: list[IRSet] = []
    for set_name, description in ontology_sets.items():
        members: str | list[Any] = instance.sets.get(set_name, "from_instance")
        ir_sets.append(
            IRSet(
                name=set_name,
                description=description,
                members=members,
            )
        )
    return ir_sets


def _build_parameters_from_instance(
    instance: OptimizationInstance,
    ontology_params: dict[str, str],
    resolved_parameters: dict[str, Any] | None = None,
) -> list[IRParameter]:
    """Build IR parameters from instance data and ontology descriptions.

    ``resolved_parameters`` may contain ontology defaults merged on top of the
    raw instance values so that the IR reflects parameters the solver will use.
    """
    params = resolved_parameters if resolved_parameters is not None else instance.parameters
    ir_params: list[IRParameter] = []
    for param_name, description in ontology_params.items():
        # Instance parameter keys use the base name (e.g. 'd' for 'd_i').
        # Infer index sets from parameter name subscript
        parts = param_name.split("_", 1)
        base = parts[0]
        subscript = parts[1] if len(parts) > 1 else ""
        sets = [ch.upper() for ch in subscript if ch.isalpha() and ch.upper() in instance.sets]
        actual_value = params.get(param_name) or params.get(base)
        source = f"instance:{param_name}" if actual_value is not None else "missing"
        ir_params.append(
            IRParameter(
                name=param_name,
                description=description,
                sets=sets,
                dtype="float",
                source=source,
            )
        )
    return ir_params


def _build_variables_from_ontology(
    knowledge: KnowledgePackage,
) -> list[IRVariable]:
    """Build IR variables from ontology variable templates."""
    ir_vars: list[IRVariable] = []
    for vt in knowledge.variables:
        ir_vars.append(
            IRVariable(
                name=vt.name,
                description=vt.description,
                sets=vt.indices,
                domain=_map_variable_kind(vt.kind),
                lower=vt.lower_bound,
                upper=vt.upper_bound,
            )
        )
    return ir_vars


def _build_constraints_from_ontology(
    knowledge: KnowledgePackage,
) -> list[IRConstraint]:
    """Build IR constraints from ontology constraint templates."""
    ir_constraints: list[IRConstraint] = []
    sense_map = {"<=": "le", ">=": "ge", "==": "eq"}
    for ct in knowledge.constraints:
        constraint = IRConstraint(
            name=ct.name,
            expr=ct.expression,
            scope=ct.scope,
            sense=sense_map.get(ct.sense.value, "le"),
            rhs=ct.rhs,
            description=ct.description,
        )
        constraint.latex = _constraint_to_latex(constraint)
        ir_constraints.append(constraint)
    return ir_constraints


def _resolve_instance_parameters(
    entry: Any,
    instance: OptimizationInstance,
) -> dict[str, Any]:
    """Build the parameter dict the solver will see.

    Expands aliases, applies ontology defaults, and injects problem-specific
    derived values such as the inventory big-M.
    """
    resolved: dict[str, Any] = dict(instance.parameters)
    aliases = entry.aliases or {}

    # Expand base names to canonical names (e.g. d -> d_i).
    for base, canonical_list in aliases.items():
        if base in resolved:
            for alias in canonical_list:
                if alias not in resolved:
                    resolved[alias] = resolved[base]

    # Apply ontology defaults for parameters that are absent.
    defaults = entry.defaults or {}
    for base, value in defaults.items():
        if base not in resolved:
            resolved[base] = value
            for alias in aliases.get(base, []):
                if alias not in resolved:
                    resolved[alias] = value

    # Inject a scalar big-M for inventory linking constraints when absent.
    if entry.problem_type == "inventory" and "M" not in resolved:
        d_param = resolved.get("d_it")
        if isinstance(d_param, dict):
            with contextlib.suppress(Exception):
                resolved["M"] = max(
                    sum(float(v) for v in item_demands.values())
                    for item_demands in d_param.values()
                )

    # Inject a scalar big-M for scheduling disjunctive constraints when absent.
    if entry.problem_type == "scheduling" and "M" not in resolved:
        p_param = resolved.get("p_j") or resolved.get("p")
        if isinstance(p_param, dict):
            with contextlib.suppress(Exception):
                resolved["M"] = sum(float(v) for v in p_param.values())

    return resolved


def _missing_required_parameters(
    knowledge: KnowledgePackage,
    instance: OptimizationInstance,
    resolved_parameters: dict[str, Any] | None = None,
) -> list[str]:
    """Return ontology parameter symbols that are missing from the instance.

    A symbol is considered present if either its canonical name or its base
    name is found in ``instance.parameters`` (or in the optional resolved view).
    """
    entry = knowledge.ontology_entry
    sig = entry.signature or {}
    required = set(sig.get("required_parameters", []))
    if not required:
        required = set(entry.parameters.keys())

    param_source = resolved_parameters if resolved_parameters is not None else instance.parameters
    present = set(param_source.keys())
    present_bases = {p.split("_", 1)[0] for p in present if "_" in p}
    present_bases.update(p for p in present if "_" not in p)

    missing: list[str] = []
    for symbol in required:
        base = symbol.split("_", 1)[0] if "_" in symbol else symbol
        if symbol not in present and base not in present_bases:
            missing.append(symbol)

    # The backend automatically computes parameters declared in the ontology
    # (e.g. big-M constants for inventory and scheduling); they are not
    # user-facing parameters.
    auto_computed = set(entry.signature.get("auto_computed_parameters", []))
    return [s for s in missing if s not in auto_computed]


class IRGenerator:
    """Generates an IRModel from a KnowledgePackage + OptimizationInstance.

    The generator is deterministic: given the same inputs it produces the same
    IR. LLM direct IR generation has been removed per the ontology-rework
    architecture; missing parameters are now handled by the ontology patch
    layer.
    """

    def __init__(
        self,
        llm_generator: Any | None = None,
        use_llm: bool | None = None,
    ) -> None:
        """Initialize the generator.

        ``llm_generator`` and ``use_llm`` are accepted for backwards
        compatibility but no longer affect generation.
        """
        del llm_generator, use_llm

    def generate(
        self,
        knowledge: KnowledgePackage,
        instance: OptimizationInstance,
    ) -> IRModel:
        """Build the full IR model from knowledge and instance data."""
        entry = knowledge.ontology_entry

        # Resolve aliases, defaults, and problem-specific derived parameters.
        resolved_parameters = _resolve_instance_parameters(entry, instance)

        sets = _build_sets_from_instance(instance, entry.sets)
        parameters = _build_parameters_from_instance(
            instance, entry.parameters, resolved_parameters
        )
        variables = _build_variables_from_ontology(knowledge)
        constraints = _build_constraints_from_ontology(knowledge)

        # For rectangular (or square) bipartite matching, force the maximum
        # number of assignments so the trivial zero solution is not optimal.
        if knowledge.problem_type.value == "assignment":
            i_members = instance.sets.get("I", [])
            j_members = instance.sets.get("J", [])
            if isinstance(i_members, (list, tuple, set)) and isinstance(
                j_members, (list, tuple, set)
            ):
                min_card = min(len(i_members), len(j_members))
                min_card_constraint = IRConstraint(
                    name="min_cardinality",
                    expr="sum_{i in I} sum_{j in J} x_ij",
                    scope="",
                    sense="ge",
                    rhs=str(min_card),
                    description="Assign at least min(|I|, |J|) agent-task pairs",
                )
                min_card_constraint.latex = _constraint_to_latex(min_card_constraint)
                constraints.append(min_card_constraint)

        # For continuous-time scheduling, build the unordered pair set P used by
        # the disjunctive constraints and make sure it has explicit members.
        if knowledge.problem_type.value == "scheduling":
            jobs = instance.sets.get("J", [])
            if isinstance(jobs, (list, tuple)):
                pairs = [f"{j}_{k}" for idx, j in enumerate(jobs) for k in jobs[idx + 1 :]]
                existing = {s.name: i for i, s in enumerate(sets)}
                if "P" in existing:
                    sets[existing["P"]] = IRSet(
                        name="P",
                        description="unordered job pairs",
                        members=pairs,
                    )
                else:
                    sets.append(
                        IRSet(
                            name="P",
                            description="unordered job pairs",
                            members=pairs,
                        )
                    )

        # Build objective expression
        objective_expr: IRExpression | None = None
        if knowledge.objective:
            objective_expr = _parse_objective_expression(knowledge.objective.expression)
            sense = "minimize" if knowledge.objective.sense.value == "minimize" else "maximize"
        else:
            sense = "minimize"

        return IRModel(
            meta={
                "schema_version": SCHEMA_VERSION,
                "problem_type": knowledge.problem_type.value,
                "dataset_id": instance.meta.get("dataset_id", ""),
                "instance_parameters": resolved_parameters,
            },
            problem_type=knowledge.problem_type.value,
            sense=sense,
            sets=sets,
            parameters=parameters,
            variables=variables,
            objective=objective_expr,
            constraints=constraints,
        )

    def generate_from_state(self, state: dict[str, Any]) -> IRModel:
        """Generate IR from workflow state dict (for workflow integration)."""
        kp_data = state.get("knowledge_package")
        inst_data = state.get("instance")
        if not kp_data or not inst_data:
            raise ValueError("Missing knowledge_package or instance in state")

        knowledge = KnowledgePackage.model_validate(kp_data)
        instance = OptimizationInstance.model_validate(inst_data)
        return self.generate(knowledge, instance)

    def generate_from_state_with_diagnostics(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate IR and expose diagnostics for the workflow node.

        Returns a dict with keys:
            ir: IRModel
            missing_parameters: list[str]
            assumptions: list[str]
            used_llm: bool
            confidence: float
        """
        inst_data = state.get("instance")
        if not inst_data:
            raise ValueError("Missing instance in state")

        instance = OptimizationInstance.model_validate(inst_data)
        kp_data = state.get("knowledge_package")
        if not kp_data:
            raise ValueError("Missing knowledge_package in state")

        knowledge = KnowledgePackage.model_validate(kp_data)
        ir_model = self.generate(knowledge, instance)
        resolved_parameters = _resolve_instance_parameters(knowledge.ontology_entry, instance)
        missing = _missing_required_parameters(knowledge, instance, resolved_parameters)

        return {
            "ir": ir_model,
            "missing_parameters": missing,
            "assumptions": ir_model.meta.get("llm_assumptions", []),
            "used_llm": False,
            "confidence": 1.0,
        }

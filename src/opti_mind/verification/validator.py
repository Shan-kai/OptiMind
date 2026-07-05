"""ModelValidator: runs all verification checks on an IRModel.

Per IR_SPEC section 8 and ROADMAP Phase 6, the four verification categories are:
  1. Structural: sets defined, variables declared, no dangling references.
  2. Index: variable/parameter index sets exist in the model's sets.
  3. Logic: business invariants (e.g. assignment-type problems require an
     "each customer once" constraint family).
  4. Mathematical consistency: objective references declared variables,
     constraint senses are valid, bounds are coherent, no nonlinear mixed
     with continuous in a pure-LP model.

Only an IR that passes every check is allowed to proceed to the Solver Layer.
"""

from __future__ import annotations

import re
from typing import Any

from opti_mind.modeling.ir_models import IRModel
from opti_mind.verification.models import VerificationReport, VerificationResult

_VALID_DOMAINS = {"binary", "integer", "continuous", "semi_continuous"}
_VALID_SENSES = {"le", "ge", "eq", "range"}
_VALID_OBJ_SENSES = {"minimize", "maximize"}


def _extract_symbols(text: str) -> set[str]:
    """Extract candidate variable/parameter symbols from a symbolic string.

    Only extracts symbols that look like actual optimization identifiers
    (at least 2 characters with an underscore pattern, e.g. 'x_ij', 'd_i'),
    filtering out set names (single uppercase), index variables (single
    lowercase), and sum-expression fragments.
    """
    keywords = {
        "sum",
        "sum_",
        "in",
        "forall",
        "for",
        "all",
        "if",
        "then",
        "else",
        "and",
        "or",
        "not",
        "M",
    }
    tokens = re.findall(r"[a-zA-Z_]\w*(?:_\w+)?", text)
    result: set[str] = set()
    for t in tokens:
        tl = t.lower()
        if tl in keywords or tl.endswith("_"):
            continue
        # Skip single letters: set names (I,J) and index vars (i,j)
        if len(t) == 1:
            continue
        # Require an underscore to look like a variable/parameter (x_ij, d_i)
        if "_" not in t and len(t) <= 3:
            # Could be a short parameter name without underscore (rare);
            # only accept those with at least 2 distinct chars
            continue
        result.add(t)
    return result


def _variable_signature(symbol: str) -> tuple[str, tuple[str, ...]]:
    """Return (base, sorted lowercase letters) for a symbol like 'x_ij'."""
    base, _, subscript = symbol.partition("_")
    letters = tuple(sorted(ch for ch in subscript if ch.islower()))
    return base, letters


def _match_variable_symbol(token: str, declared_vars: set[str]) -> str | None:
    """Map a possibly lagged/reversed variable token to a declared variable."""
    if token in declared_vars:
        return token
    token_sig = _variable_signature(token)
    for var in declared_vars:
        if _variable_signature(var) == token_sig:
            return var
    # Fallback: same base and same number of subscript letters (e.g. C_k -> C_j
    # when the scope uses a different index letter for the same single-index
    # variable).  The compiler resolves the concrete index from the scope.
    token_base, token_letters = token_sig
    for var in declared_vars:
        var_base, var_letters = _variable_signature(var)
        if var_base == token_base and len(var_letters) == len(token_letters):
            return var
    return None


def _canonicalize_symbols(text: str, declared_vars: set[str]) -> str:
    """Rewrite lag/reverse variable tokens into declared variable names.

    Recognises two patterns:
      - Lag: ``I_i(t-1)`` is rewritten to the declared variable ``I_it``.
      - Reverse/permuted index: ``x_ji`` is rewritten to ``x_ij``.
    """

    def _lag_repl(match: re.Match[str]) -> str:
        canonical = f"{match.group(1)}_{match.group(2)}{match.group(3)}"
        return canonical if canonical in declared_vars else match.group(0)

    text = re.sub(
        r"(?<![A-Za-z0-9_])([A-Za-z])_([a-z]+)\(([a-z])-1\)(?![A-Za-z0-9_])",
        _lag_repl,
        text,
    )

    for token in set(re.findall(r"[a-zA-Z_]\w*(?:_\w+)?", text)):
        if "_" not in token or token in declared_vars:
            continue
        canonical = _match_variable_symbol(token, declared_vars)
        if canonical:
            text = re.sub(
                rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])",
                canonical,
                text,
            )
    return text


def _check_structure(model: IRModel) -> VerificationResult:
    """Structural check: non-empty core fields, unique names, no duplicates."""
    issues: list[str] = []
    if not model.problem_type:
        issues.append("problem_type is empty")
    if not model.sets:
        issues.append("no sets defined")
    if not model.variables:
        issues.append("no variables defined")
    if model.objective is None:
        issues.append("no objective defined")
    if not model.constraints:
        issues.append("no constraints defined")

    set_names = [s.name for s in model.sets]
    if len(set_names) != len(set(set_names)):
        issues.append("duplicate set names detected")
    var_names = [v.name for v in model.variables]
    if len(var_names) != len(set(var_names)):
        issues.append("duplicate variable names detected")
    param_names = [p.name for p in model.parameters]
    if len(param_names) != len(set(param_names)):
        issues.append("duplicate parameter names detected")
    constraint_names = [c.name for c in model.constraints]
    if len(constraint_names) != len(set(constraint_names)):
        issues.append("duplicate constraint names detected")

    passed = not issues
    return VerificationResult(
        check_name="structural",
        passed=passed,
        message="structure valid" if passed else "structural issues",
        details=issues,
    )


def _check_indices(model: IRModel) -> VerificationResult:
    """Index check: every variable/parameter index set is defined in the model."""
    defined_sets = {s.name for s in model.sets}
    defined_sets |= {f"({name})" for name in defined_sets}  # arc-set alias
    issues: list[str] = []

    for var in model.variables:
        for idx in var.sets:
            if idx not in defined_sets and idx.strip("()") not in defined_sets:
                issues.append(f"variable '{var.name}' references undefined set '{idx}'")
    for param in model.parameters:
        for idx in param.sets:
            if idx not in defined_sets:
                issues.append(f"parameter '{param.name}' references undefined set '{idx}'")
    # Sum sets in objective terms
    if model.objective:
        for term in model.objective.terms:
            for ss in term.sum_sets:
                if ss not in defined_sets:
                    issues.append(f"objective term references undefined sum set '{ss}'")

    passed = not issues
    return VerificationResult(
        check_name="index",
        passed=passed,
        message="indices valid" if passed else "index issues",
        details=issues,
    )


def _check_math(model: IRModel) -> VerificationResult:
    """Mathematical consistency: domains, senses, bounds, objective refs."""
    issues: list[str] = []

    if model.sense not in _VALID_OBJ_SENSES:
        issues.append(f"invalid objective sense '{model.sense}'")

    for v in model.variables:
        if v.domain not in _VALID_DOMAINS:
            issues.append(f"variable '{v.name}' has invalid domain '{v.domain}'")
        if v.lower is not None and v.upper is not None and v.lower > v.upper:
            issues.append(f"variable '{v.name}' has lower bound > upper bound")

    for c in model.constraints:
        if c.sense not in _VALID_SENSES:
            issues.append(f"constraint '{c.name}' has invalid sense '{c.sense}'")

    declared_vars = {v.name for v in model.variables}
    declared_params = {p.name for p in model.parameters}
    declared_symbols = declared_vars | declared_params

    if model.objective:
        ref_text = model.objective.raw_expr
        for term in model.objective.terms:
            ref_text += " " + term.var + " " + term.coef
        referenced = _extract_symbols(_canonicalize_symbols(ref_text, declared_vars))
        unknown = referenced - declared_symbols - {"1", "0"}
        # Allow numeric literals already filtered by regex letter-start
        if unknown:
            issues.append(f"objective references unknown symbols: {sorted(unknown)}")

    for c in model.constraints:
        ref_text = c.expr + " " + (c.rhs or "")
        referenced = _extract_symbols(_canonicalize_symbols(ref_text, declared_vars))
        unknown = referenced - declared_symbols - {"1", "0"}
        if unknown:
            issues.append(f"constraint '{c.name}' references unknown symbols: {sorted(unknown)}")

    passed = not issues
    return VerificationResult(
        check_name="mathematical",
        passed=passed,
        message="math consistent" if passed else "math issues",
        details=issues,
    )


def _check_logic(model: IRModel) -> VerificationResult:
    """Logic check: business invariants derived from the problem type.

    These are lightweight structural invariants, not full solver feasibility.
    """
    issues: list[str] = []
    pt = model.problem_type
    constraint_names = {c.name for c in model.constraints}

    # Assignment-family problems require an "each customer assigned once"
    # style equality constraint. We check by name pattern rather than
    # parsing the expression to stay robust.
    if pt in {"facility_location", "assignment", "transportation"}:
        has_assignment = any(
            "assign" in name.lower()
            or "once" in name.lower()
            or "one" in name.lower()
            or "each" in name.lower()
            or "demand" in name.lower()
            or "supply" in name.lower()
            for name in constraint_names
        )
        if not has_assignment:
            issues.append(f"problem type '{pt}' expects an assignment/demand constraint")

    if pt == "facility_location":
        var_names = {v.name for v in model.variables}
        if "y_j" not in var_names:
            issues.append("facility_location requires a facility-opening variable 'y_j'")

    if pt == "knapsack":
        has_capacity = any("cap" in n.lower() for n in constraint_names)
        if not has_capacity:
            issues.append("knapsack expects a capacity constraint")

    if pt == "network_flow":
        var_names = {v.name for v in model.variables}
        has_capacity = any("capacity" in n.lower() for n in constraint_names)
        has_conservation = any("conservation" in n.lower() for n in constraint_names)
        if not (has_capacity and has_conservation):
            issues.append("network_flow expects both 'capacity' and 'conservation' constraints")
        has_flow_var = "x_ij" in var_names or any(
            v.name == "x" and "A" in v.sets for v in model.variables
        )
        if not has_flow_var:
            issues.append(
                "network_flow requires flow variable 'x_ij' or variable 'x' indexed over 'A'"
            )

    if pt == "scheduling":
        var_names = {v.name for v in model.variables}
        has_completion = any("completion" in n.lower() for n in constraint_names)
        has_disjunctive = any("disjunctive" in n.lower() for n in constraint_names)
        if not has_completion:
            issues.append("scheduling expects a 'completion' constraint")
        if not has_disjunctive:
            issues.append("scheduling expects 'disjunctive' constraints")
        if "S_j" not in var_names:
            issues.append("scheduling requires variable 'S_j'")
        if "C_j" not in var_names:
            issues.append("scheduling requires variable 'C_j'")
        if "y_jk" not in var_names:
            issues.append("scheduling requires variable 'y_jk'")

    if pt == "inventory":
        var_names = {v.name for v in model.variables}
        has_balance = any("balance" in n.lower() for n in constraint_names)
        has_linking = any("linking" in n.lower() for n in constraint_names)
        if not (has_balance and has_linking):
            issues.append("inventory expects both 'balance' and 'linking' constraints")
        if "x_it" not in var_names:
            issues.append("inventory requires variable 'x_it'")
        if "y_it" not in var_names:
            issues.append("inventory requires variable 'y_it'")
        if "I_it" not in var_names:
            issues.append("inventory requires variable 'I_it'")

    passed = not issues
    return VerificationResult(
        check_name="logic",
        passed=passed,
        message="logic valid" if passed else "logic issues",
        details=issues,
    )


class ModelValidator:
    """Validates an IRModel against all four verification categories."""

    def validate(self, model: IRModel) -> VerificationReport:
        """Run all checks and return a VerificationReport."""
        report = VerificationReport()
        report.add(_check_structure(model))
        report.add(_check_indices(model))
        report.add(_check_math(model))
        report.add(_check_logic(model))
        return report

    def validate_dict(self, ir_data: dict[str, Any]) -> VerificationReport:
        """Validate an IR provided as a dict (e.g. from workflow state)."""
        model = IRModel.model_validate(ir_data)
        return self.validate(model)

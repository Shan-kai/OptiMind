"""Compile IR to a docplex Model for solving via CPLEX.

The compiler walks the IR structure (sets, parameters, variables, objective,
constraints) and constructs an equivalent docplex.mp.model.Model that CPLEX
can solve. Only deterministic logic lives here.
"""

from __future__ import annotations

import ast
import re
from typing import Any, NamedTuple

from docplex.mp.model import Model

from opti_mind.modeling.ir_models import IRModel, IRVariable


class IRToModelCompiler:
    """Compiles an IRModel into a runnable docplex Model."""

    def compile(self, ir: IRModel) -> tuple[Model, dict[str, Any]]:
        """Build a docplex Model from IR.

        Returns:
            (model, var_index) where var_index maps IR variable names
            to their docplex variable objects for later solution extraction.

        """
        model = Model(name=ir.problem_type)
        model.set_time_limit(300)

        set_members = self._build_set_members(ir)
        arc_lookup = self._build_arc_lookup(ir.sets, set_members)
        params = self._build_params(ir)

        var_index: dict[str, Any] = {}
        var_defs: dict[str, IRVariable] = {}
        for var_def in ir.variables:
            var_obj = self._declare_variable(model, var_def, set_members)
            var_index[var_def.name] = var_obj
            var_defs[var_def.name] = var_def

        if ir.objective:
            obj_expr = self._build_expression(ir.objective.terms, var_index, set_members, params)
            if ir.sense == "maximize":
                model.maximize(obj_expr)
            else:
                model.minimize(obj_expr)

        for constraint in ir.constraints:
            self._add_constraint(
                model, constraint, var_index, var_defs, set_members, params, arc_lookup
            )

        return model, var_index

    @staticmethod
    def _build_set_members(ir: IRModel) -> dict[str, list[Any]]:
        """Extract set member lists from the IR."""
        result: dict[str, list[Any]] = {}
        for s in ir.sets:
            if isinstance(s.members, list):
                result[s.name] = s.members
            else:
                result[s.name] = list(range(3))
        return result

    @staticmethod
    def _build_params(ir: IRModel) -> dict[str, Any]:
        """Extract parameter values from IR metadata."""
        return dict(ir.meta.get("instance_parameters", {}))

    @staticmethod
    def _declare_variable(
        model: Model,
        var_def: IRVariable,
        set_members: dict[str, list[Any]],
    ) -> Any:
        """Create a docplex variable (or var_dict over indices)."""
        domain = var_def.domain
        lb = var_def.lower if var_def.lower is not None else 0
        ub = var_def.upper

        if not var_def.sets:
            if domain == "binary":
                return model.binary_var(name=var_def.name)
            if domain == "integer":
                return model.integer_var(lb=lb, ub=ub, name=var_def.name)
            return model.continuous_var(lb=lb, ub=ub, name=var_def.name)

        indices = IRToModelCompiler._cartesian(
            [set_members.get(s, list(range(3))) for s in var_def.sets]
        )
        var_dict: dict[Any, Any] = {}
        for idx_tuple in indices:
            vname = f"{var_def.name}_{'_'.join(str(i) for i in idx_tuple)}"
            key: Any = idx_tuple[0] if len(idx_tuple) == 1 else idx_tuple
            if domain == "binary":
                var_dict[key] = model.binary_var(name=vname)
            elif domain == "integer":
                var_dict[key] = model.integer_var(lb=lb, ub=ub, name=vname)
            else:
                var_dict[key] = model.continuous_var(lb=lb, ub=ub, name=vname)
        return var_dict

    @staticmethod
    def _cartesian(lists: list[list[Any]]) -> list[tuple[Any, ...]]:
        """Compute Cartesian product of index lists."""
        if not lists:
            return [()]
        result: list[tuple[Any, ...]] = [()]
        for lst in lists:
            result = [r + (e,) for r in result for e in lst]
        return result

    @staticmethod
    def _infer_index_count(symbol: str) -> int:
        """Infer how many indices a parameter symbol expects from its subscript.

        Examples:
            c_ij  -> 2   (subscript 'ij')
            d_i   -> 1   (subscript 'i')
            f_j   -> 1   (subscript 'j')
        """
        parts = symbol.split("_", 1)
        if len(parts) <= 1:
            return 0
        return sum(1 for ch in parts[1] if ch.islower())

    @staticmethod
    def _lookup_coef(factor_name: str, coef_data: Any, indices: tuple[Any, ...]) -> float | None:
        """Extract the coefficient matching a variable's indices.

        Only consumes the leading ``indices`` needed by ``factor_name`` so
        parameters with fewer subscripts (e.g. ``d_i``) can be combined with
        variables indexed over more sets (e.g. ``x_ij``).
        """
        value = coef_data
        index_count = IRToModelCompiler._infer_index_count(factor_name)
        try:
            for idx in indices[:index_count]:
                value = value[str(idx)]
            return float(value)
        except (TypeError, KeyError, ValueError):
            if isinstance(value, (int, float)):
                return float(value)
            return None

    @staticmethod
    def _eval_coef(coef_str: str, indices: tuple[Any, ...], params: dict[str, Any]) -> float:
        """Evaluate a coefficient string that may be a product of parameters."""
        if not coef_str or coef_str == "1":
            return 1.0
        factors = [f.strip() for f in coef_str.split("*") if f.strip()]
        value = 1.0
        for factor in factors:
            # Numeric literal (including '1' or '-1').
            try:
                value *= float(factor)
                continue
            except ValueError:
                pass
            coef_data = params.get(factor)
            if coef_data is None:
                # Missing parameter: keep compilation robust by treating it as 1.0,
                # matching the legacy single-parameter fallback behaviour.
                continue
            factor_value = IRToModelCompiler._lookup_coef(factor, coef_data, indices)
            if factor_value is None:
                continue
            value *= factor_value
        return value

    @staticmethod
    def _build_expression(
        terms: list[Any],
        var_index: dict[str, Any],
        set_members: dict[str, list[Any]],
        params: dict[str, Any],
    ) -> Any:
        """Build a docplex linear expression from IR terms."""
        expr = None

        def add_term(e: Any, t: Any) -> Any:
            return t if e is None else e + t

        for term in terms:
            var_obj = var_index.get(term.var)
            if var_obj is None:
                continue

            if isinstance(var_obj, dict):
                term_expr = None
                for key, var in var_obj.items():
                    indices = (key,) if not isinstance(key, tuple) else key
                    coef = IRToModelCompiler._eval_coef(term.coef, indices, params)
                    term_expr = add_term(term_expr, coef * var)
                if term_expr is not None:
                    expr = add_term(expr, term_expr)
            else:
                coef = IRToModelCompiler._eval_coef(term.coef, (), params)
                expr = add_term(expr, coef * var_obj)

        return expr or 0

    # -----------------------------------------------------------------------
    # Generic constraint compiler helpers
    # -----------------------------------------------------------------------

    class _SumIndex(NamedTuple):
        """A single summation quantifier parsed from ``sum_{...}``."""

        index_expr: str
        set_name: str
        condition: str | None

    class _ExpressionTerm(NamedTuple):
        """One additive term of a symbolic expression."""

        sign: int
        coef: str
        var: str | None
        sum_indices: list[IRToModelCompiler._SumIndex]

    class _InitialLagError(Exception):
        """Raised when a lagged variable refers to the period before the horizon."""

        def __init__(self, param_name: str) -> None:
            self.param_name = param_name

    @staticmethod
    def _variable_signature(symbol: str) -> tuple[str, tuple[str, ...]]:
        """Return (base, sorted lowercase letters) for a symbol like ``x_ij``."""
        base, _, subscript = symbol.partition("_")
        letters = tuple(sorted(ch for ch in subscript if ch.islower()))
        return base, letters

    @staticmethod
    def _match_variable_symbol(token: str, declared_vars: set[str]) -> str | None:
        """Map a possibly lagged/reversed variable token to a declared variable.

        Matches first by exact name, then by signature (sorted index letters),
        and finally by base name plus index count so that expressions using
        different index letters (e.g. ``S_k`` in a ``(j,k)`` scope) resolve to
        the declared variable ``S_j``.
        """
        if token in declared_vars:
            return token
        token_sig = IRToModelCompiler._variable_signature(token)
        for var in declared_vars:
            if IRToModelCompiler._variable_signature(var) == token_sig:
                return var
        # Fallback: same base and same number of indices.
        token_base, token_letters = token_sig
        token_count = len(token_letters)
        candidates = [
            var
            for var in declared_vars
            if IRToModelCompiler._variable_signature(var)[0] == token_base
            and len(IRToModelCompiler._variable_signature(var)[1]) == token_count
        ]
        if len(candidates) == 1:
            return candidates[0]
        return None

    @staticmethod
    def _parse_scope(scope: str) -> list[tuple[str, str]]:
        """Parse a scope string into a list of (index_expr, set_name) pairs.

        Examples:
          - "for all j in J" -> [("j", "J")]
          - "forall i in I, t in T" -> [("i", "I"), ("t", "T")]
          - "for all (i,j) in A" -> [("(i,j)", "A")]
        """
        scope = scope.strip()
        if not scope:
            return []
        scope = re.sub(r"^(?:for\s+all|forall)\s+", "", scope, flags=re.IGNORECASE)
        # Split on commas that are not inside parentheses so that quantifiers
        # like "(i,j) in A" remain a single part.
        parts: list[str] = []
        current = ""
        depth = 0
        for ch in scope:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                if current.strip():
                    parts.append(current.strip())
                current = ""
                continue
            current += ch
        if current.strip():
            parts.append(current.strip())

        result: list[tuple[str, str]] = []
        for part in parts:
            m = re.match(r"^\(([^)]+)\)\s+in\s+(\w+)$", part)
            if m:
                result.append((f"({m.group(1)})", m.group(2)))
                continue
            m = re.match(r"^(\w+)\s+in\s+(\w+)$", part)
            if m:
                result.append((m.group(1), m.group(2)))
        return result

    @staticmethod
    def _parse_sum_spec(spec: str) -> IRToModelCompiler._SumIndex:
        """Parse the inside of a ``sum_{...}`` quantifier."""
        spec = spec.strip()
        condition: str | None = None
        index_expr = ""
        set_name = ""
        if ":" in spec:
            index_expr, rest = spec.split(":", 1)
            index_expr = index_expr.strip()
            condition = rest.strip()
            m = re.search(r"in\s+(\w+)", condition)
            set_name = m.group(1) if m else ""
        else:
            m = re.match(r"^(\([^)]+\)|\w+)\s+in\s+(\w+)$", spec)
            if m:
                index_expr = m.group(1)
                set_name = m.group(2)
            else:
                index_expr = spec

        return IRToModelCompiler._SumIndex(index_expr, set_name, condition)

    @staticmethod
    def _split_additive(expr: str) -> list[tuple[int, str]]:
        """Split ``expr`` into signed additive tokens, respecting parentheses."""
        tokens: list[tuple[int, str]] = []
        start = 0
        sign = 1
        depth = 0
        for i, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif depth == 0 and ch in "+-":
                body = expr[start:i].strip()
                if body:
                    tokens.append((sign, body))
                sign = -1 if ch == "-" else 1
                start = i + 1
        body = expr[start:].strip()
        if body:
            tokens.append((sign, body))
        return tokens

    @staticmethod
    def _strip_outer_parens(s: str) -> str:
        """Remove a single balanced pair of surrounding parentheses."""
        s = s.strip()
        while s.startswith("(") and s.endswith(")"):
            depth = 0
            ok = True
            for i, ch in enumerate(s):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0 and i != len(s) - 1:
                        ok = False
                        break
            if ok:
                s = s[1:-1].strip()
            else:
                break
        return s

    @staticmethod
    def _parse_expression(
        expr: str,
        declared_vars: set[str],
    ) -> list[IRToModelCompiler._ExpressionTerm]:
        """Parse a symbolic linear expression into additive terms.

        Each returned term records its sign, coefficient string, optional
        variable reference, and any leading summation quantifiers.
        """
        terms: list[IRToModelCompiler._ExpressionTerm] = []
        for sign, body in IRToModelCompiler._split_additive(expr):
            sum_indices: list[IRToModelCompiler._SumIndex] = []
            rest = body
            while True:
                m = re.match(r"sum_\{([^}]+)\}\s*(.+)", rest)
                if not m:
                    break
                sum_indices.append(IRToModelCompiler._parse_sum_spec(m.group(1)))
                rest = m.group(2).strip()

            # Split remaining product by '*' outside parentheses.
            factors: list[str] = []
            current = ""
            depth = 0
            for ch in rest:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                elif ch == "*" and depth == 0:
                    if current.strip():
                        factors.append(current.strip())
                    current = ""
                    continue
                current += ch
            if current.strip():
                factors.append(current.strip())
            factors = [IRToModelCompiler._strip_outer_parens(f) for f in factors if f.strip()]

            if not factors:
                continue

            var_token = IRToModelCompiler._match_variable_symbol(factors[-1], declared_vars)
            if var_token is not None:
                coef = " * ".join(factors[:-1]) if len(factors) > 1 else "1"
                terms.append(
                    IRToModelCompiler._ExpressionTerm(
                        sign=sign,
                        coef=coef,
                        var=factors[-1],
                        sum_indices=sum_indices,
                    )
                )
            else:
                terms.append(
                    IRToModelCompiler._ExpressionTerm(
                        sign=sign,
                        coef=" * ".join(factors),
                        var=None,
                        sum_indices=sum_indices,
                    )
                )
        return terms

    @staticmethod
    def _parse_subscript(subscript: str) -> list[tuple[str, int]]:
        """Parse a variable subscript into (index_variable, lag) pairs.

        Examples:
          - "ij" -> [("i", 0), ("j", 0)]
          - "i(t-1)" -> [("i", 0), ("t", 1)]
        """
        positions: list[tuple[str, int]] = []
        i = 0
        while i < len(subscript):
            ch = subscript[i]
            if ch.islower():
                letter = ch
                lag = 0
                i += 1
                if i < len(subscript) and subscript[i] == "(":
                    end = subscript.find(")", i)
                    if end != -1:
                        content = subscript[i + 1 : end]
                        m = re.match(r"([a-z])\s*-\s*1", content)
                        if m:
                            letter = m.group(1)
                            lag = 1
                        i = end + 1
                positions.append((letter, lag))
            else:
                i += 1
        return positions

    @staticmethod
    def _build_arc_lookup(
        sets: list[Any],
        set_members: dict[str, list[Any]],
    ) -> dict[str, dict[str, Any]]:
        """Build forward/reverse arc lookups for arc sets.

        Arc members are expected to be strings like ``"n1_n2"``.  The returned
        dictionary maps set name to ``{"fwd": {member: (src,tgt)}, "rev": {(src,tgt): member}}``.
        """
        lookup: dict[str, dict[str, Any]] = {}
        for s in sets:
            members = set_members.get(s.name, [])
            fwd: dict[Any, tuple[str, str]] = {}
            rev: dict[tuple[str, str], Any] = {}
            for member in members:
                if isinstance(member, str) and member.count("_") == 1:
                    src, tgt = member.split("_", 1)
                    fwd[member] = (src, tgt)
                    rev[(src, tgt)] = member
            if fwd:
                lookup[s.name] = {"fwd": fwd, "rev": rev}
        return lookup

    @staticmethod
    def _eval_math_expr(
        expr: str,
        indices: dict[str, Any],
        params: dict[str, Any],
    ) -> float:
        """Evaluate a simple arithmetic expression of literals, parameters and indices."""
        if not expr or expr == "1":
            return 1.0

        def _resolve_name(node: ast.Name) -> float:
            token = node.id
            if token in indices:
                try:
                    return float(indices[token])
                except (ValueError, TypeError):
                    return 0.0
            try:
                return float(token)
            except (ValueError, TypeError):
                pass
            return IRToModelCompiler._lookup_param_value(token, indices, params)

        def _eval(node: ast.AST) -> float:
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return float(node.value)
            if isinstance(node, ast.Name):
                return _resolve_name(node)
            if isinstance(node, ast.BinOp):
                left = _eval(node.left)
                right = _eval(node.right)
                if isinstance(node.op, ast.Add):
                    return left + right
                if isinstance(node.op, ast.Sub):
                    return left - right
                if isinstance(node.op, ast.Mult):
                    return left * right
                if isinstance(node.op, ast.Div):
                    return left / right if right != 0 else 0.0
            if isinstance(node, ast.UnaryOp):
                operand = _eval(node.operand)
                if isinstance(node.op, ast.UAdd):
                    return operand
                if isinstance(node.op, ast.USub):
                    return -operand
            return 1.0

        try:
            tree = ast.parse(expr, mode="eval")
            return _eval(tree.body)
        except Exception:
            return 1.0

    @staticmethod
    def _lookup_param_value(
        token: str,
        indices: dict[str, Any],
        params: dict[str, Any],
    ) -> float:
        """Return the numeric value of parameter ``token`` for the given indices."""
        data = params.get(token)
        if data is None:
            return 0.0
        if isinstance(data, (int, float)):
            return float(data)
        subscript = token.split("_", 1)[1] if "_" in token else ""
        letters = [ch for ch in subscript if ch.islower()]
        values = tuple(indices.get(ch) for ch in letters)
        value = data
        try:
            for idx in values:
                value = value[str(idx)]
            return float(value)
        except (TypeError, KeyError, ValueError):
            pass
        # Fallback for arc-keyed parameters such as ``u_ij`` over ``A``.
        if values:
            arc_key = "_".join(str(v) for v in values)
            try:
                return float(data.get(arc_key, 0.0))
            except (TypeError, ValueError):
                pass
        return 1.0

    @staticmethod
    def _iter_scope(
        scopes: list[tuple[str, str]],
        set_members: dict[str, list[Any]],
        arc_lookup: dict[str, dict[str, Any]],
    ) -> Any:
        """Yield index dicts for every combination quantified by ``scopes``."""
        if not scopes:
            yield {}
            return
        index_expr, set_name = scopes[0]
        rest = scopes[1:]
        for assignment in IRToModelCompiler._iter_single_quantifier(
            index_expr, set_name, set_members, arc_lookup
        ):
            for rest_assign in IRToModelCompiler._iter_scope(rest, set_members, arc_lookup):
                yield {**assignment, **rest_assign}

    @staticmethod
    def _iter_single_quantifier(
        index_expr: str,
        set_name: str,
        set_members: dict[str, list[Any]],
        arc_lookup: dict[str, dict[str, Any]],
    ) -> Any:
        """Yield index assignments for one scope quantifier."""
        members = set_members.get(set_name, [])
        if index_expr.startswith("(") and index_expr.endswith(")"):
            vars_list = [v.strip() for v in index_expr[1:-1].split(",")]
            fwd = arc_lookup.get(set_name, {}).get("fwd", {})
            for member in members:
                arc_tuple = fwd.get(member)
                if arc_tuple is None or len(arc_tuple) != len(vars_list):
                    continue
                yield dict(zip(vars_list, arc_tuple, strict=False))
        else:
            for member in members:
                yield {index_expr: member}

    @staticmethod
    def _iter_sum_assignments(
        sum_indices: list[IRToModelCompiler._SumIndex],
        base_indices: dict[str, Any],
        set_members: dict[str, list[Any]],
        arc_lookup: dict[str, dict[str, Any]],
    ) -> Any:
        """Yield all assignments for a list of summation quantifiers."""
        if not sum_indices:
            yield {}
            return
        first = sum_indices[0]
        rest = sum_indices[1:]
        for assignment in IRToModelCompiler._iter_single_sum(
            first, base_indices, set_members, arc_lookup
        ):
            combined = {**base_indices, **assignment}
            for rest_assign in IRToModelCompiler._iter_sum_assignments(
                rest, combined, set_members, arc_lookup
            ):
                yield {**assignment, **rest_assign}

    @staticmethod
    def _iter_single_sum(
        sum_index: IRToModelCompiler._SumIndex,
        base_indices: dict[str, Any],
        set_members: dict[str, list[Any]],
        arc_lookup: dict[str, dict[str, Any]],
    ) -> Any:
        """Yield assignments for one summation quantifier."""
        set_name = sum_index.set_name
        members = set_members.get(set_name, [])
        if sum_index.condition:
            # e.g. "(i,j) in A" or "(j,i) in A"
            cond = sum_index.condition
            m = re.match(r"^\(([^)]+)\)\s+in\s+(\w+)$", cond)
            if not m:
                return
            vars_list = [v.strip() for v in m.group(1).split(",")]
            cond_set = m.group(2)
            fwd = arc_lookup.get(cond_set, {}).get("fwd", {})
            for member in set_members.get(cond_set, []):
                arc_tuple = fwd.get(member)
                if arc_tuple is None or len(arc_tuple) != len(vars_list):
                    continue
                ok = True
                assignment: dict[str, Any] = {}
                for var, val in zip(vars_list, arc_tuple, strict=False):
                    if var in base_indices and base_indices[var] != val:
                        ok = False
                        break
                    assignment[var] = val
                if ok:
                    yield assignment
        elif sum_index.index_expr.startswith("(") and sum_index.index_expr.endswith(")"):
            vars_list = [v.strip() for v in sum_index.index_expr[1:-1].split(",")]
            fwd = arc_lookup.get(set_name, {}).get("fwd", {})
            for member in members:
                arc_tuple = fwd.get(member)
                if arc_tuple is None or len(arc_tuple) != len(vars_list):
                    continue
                yield dict(zip(vars_list, arc_tuple, strict=False))
        else:
            var = sum_index.index_expr
            for member in members:
                yield {var: member}

    @staticmethod
    def _resolve_var_key(
        term_var: str,
        var_defs: dict[str, IRVariable],
        indices: dict[str, Any],
        set_members: dict[str, list[Any]],
        arc_lookup: dict[str, dict[str, Any]],
    ) -> tuple[str, Any]:
        """Map a variable token (possibly lagged/reversed) to a concrete index key.

        Returns ``(canonical_var_name, key)``.  When a lagged reference falls
        before the first period, raises ``_InitialLagError`` with the name of
        the initial-value parameter to use instead.
        """
        canonical = IRToModelCompiler._match_variable_symbol(term_var, set(var_defs.keys()))
        if canonical is None:
            raise IRToModelCompiler._InitialLagError("")
        var_def = var_defs[canonical]
        subscript = canonical.split("_", 1)[1] if "_" in canonical else ""
        index_names = [ch for ch in subscript if ch.islower()]

        token_subscript = term_var.split("_", 1)[1] if "_" in term_var else ""
        positions = IRToModelCompiler._parse_subscript(token_subscript)
        letter_to_value: dict[str, Any] = {}
        initial_lag_param: str | None = None
        for letter, lag in positions:
            if lag:
                # Find the set this lagged index belongs to.
                set_name = None
                for idx_name, sname in zip(index_names, var_def.sets, strict=False):
                    if idx_name == letter:
                        set_name = sname
                        break
                if set_name is None:
                    set_name = var_def.sets[0] if var_def.sets else None
                members = set_members.get(set_name, []) if set_name else []
                current_val = indices.get(letter)
                if current_val is None or current_val not in members:
                    lagged_val = current_val
                else:
                    pos = members.index(current_val)
                    if pos == 0:
                        # Use initial-value parameter, e.g. I0_i.
                        other_letters = [idx for idx in index_names if idx != letter]
                        other = "".join(other_letters)
                        if other:
                            initial_lag_param = f"{canonical[0]}0_{other}"
                        else:
                            initial_lag_param = f"{canonical[0]}0"
                        continue
                    lagged_val = members[pos - 1]
                letter_to_value[letter] = lagged_val
            else:
                letter_to_value[letter] = indices.get(letter)

        if initial_lag_param is not None:
            raise IRToModelCompiler._InitialLagError(initial_lag_param)

        # Build target values in declared index order.  For a reversed token
        # such as ``x_ji``, the term positions are taken in order, which swaps
        # the values relative to the declared (i,j) ordering.
        target_values: list[Any] = [letter_to_value[letter] for letter, _ in positions]

        if len(var_def.sets) == 1:
            set_name = var_def.sets[0]
            if set_name in arc_lookup:
                key = tuple(target_values)
                member = arc_lookup[set_name]["rev"].get(key)
                if member is None:
                    raise IRToModelCompiler._InitialLagError("")
                return canonical, member
            return canonical, target_values[0]
        return canonical, tuple(target_values)

    @staticmethod
    def _compile_constraint_rows(
        constraint: Any,
        var_defs: dict[str, IRVariable],
        set_members: dict[str, list[Any]],
        params: dict[str, Any],
        arc_lookup: dict[str, dict[str, Any]],
    ) -> Any:
        """Expand a constraint into rows of abstract linear terms.

        Yields ``(row_key, entries, rhs_constant)`` where ``entries`` is a list
        of ``(var_name, var_key, coefficient)`` and the final constraint is
        ``sum(entries) ==/<=/>= -rhs_constant`` after moving the RHS to the LHS.
        """
        declared_vars = set(var_defs.keys())
        lhs_terms = IRToModelCompiler._parse_expression(constraint.expr, declared_vars)
        rhs_terms = IRToModelCompiler._parse_expression(constraint.rhs or "0", declared_vars)
        terms = lhs_terms + [
            IRToModelCompiler._ExpressionTerm(
                sign=-t.sign,
                coef=t.coef,
                var=t.var,
                sum_indices=t.sum_indices,
            )
            for t in rhs_terms
        ]
        scopes = IRToModelCompiler._parse_scope(constraint.scope)
        scope_vars: list[str] = []
        for index_expr, _ in scopes:
            if index_expr.startswith("("):
                scope_vars.extend(v.strip() for v in index_expr[1:-1].split(","))
            else:
                scope_vars.append(index_expr)

        for base_indices in IRToModelCompiler._iter_scope(scopes, set_members, arc_lookup):
            entries: list[tuple[str, Any, float]] = []
            constant = 0.0
            for term in terms:
                if term.sum_indices:
                    for sum_assign in IRToModelCompiler._iter_sum_assignments(
                        term.sum_indices, base_indices, set_members, arc_lookup
                    ):
                        idx = {**base_indices, **sum_assign}
                        coef = term.sign * IRToModelCompiler._eval_math_expr(term.coef, idx, params)
                        if term.var is None:
                            constant += coef
                        else:
                            try:
                                var_name, var_key = IRToModelCompiler._resolve_var_key(
                                    term.var, var_defs, idx, set_members, arc_lookup
                                )
                            except IRToModelCompiler._InitialLagError as exc:
                                if exc.param_name:
                                    constant += coef * IRToModelCompiler._eval_math_expr(
                                        exc.param_name, idx, params
                                    )
                                continue
                            entries.append((var_name, var_key, coef))
                else:
                    idx = base_indices
                    coef = term.sign * IRToModelCompiler._eval_math_expr(term.coef, idx, params)
                    if term.var is None:
                        constant += coef
                    else:
                        try:
                            var_name, var_key = IRToModelCompiler._resolve_var_key(
                                term.var, var_defs, idx, set_members, arc_lookup
                            )
                        except IRToModelCompiler._InitialLagError as exc:
                            if exc.param_name:
                                constant += coef * IRToModelCompiler._eval_math_expr(
                                    exc.param_name, idx, params
                                )
                            continue
                        entries.append((var_name, var_key, coef))

            if not scope_vars:
                row_key = None
            elif len(scope_vars) == 1:
                row_key = base_indices.get(scope_vars[0])
            else:
                row_key = tuple(base_indices.get(v) for v in scope_vars)
            yield row_key, entries, -constant

    @staticmethod
    def _add_constraint(
        model: Model,
        constraint: Any,
        var_index: dict[str, Any],
        var_defs: dict[str, IRVariable],
        set_members: dict[str, list[Any]],
        params: dict[str, Any],
        arc_lookup: dict[str, dict[str, Any]],
    ) -> None:
        """Add a constraint to the docplex model using generic scope parsing."""
        for _row_key, entries, rhs_constant in IRToModelCompiler._compile_constraint_rows(
            constraint, var_defs, set_members, params, arc_lookup
        ):
            expr = None
            for var_name, var_key, coef in entries:
                var_obj = var_index.get(var_name)
                if var_obj is None:
                    continue
                if isinstance(var_obj, dict):
                    var = var_obj.get(var_key)
                    if var is None:
                        continue
                else:
                    var = var_obj
                term = coef * var
                expr = term if expr is None else expr + term
            IRToModelCompiler._add_sense(model, expr or 0, rhs_constant, constraint.sense)

    @staticmethod
    def _add_sense(model: Model, lhs: Any, rhs: Any, sense: str) -> None:
        """Add a constraint with the given sense."""
        if sense == "eq":
            model.add_constraint(lhs == rhs)
        elif sense == "le":
            model.add_constraint(lhs <= rhs)
        elif sense == "ge":
            model.add_constraint(lhs >= rhs)

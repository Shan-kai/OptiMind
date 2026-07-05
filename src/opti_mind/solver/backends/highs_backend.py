"""HiGHS backend: compiles IR to a HighsLp model and solves with HiGHS."""

from __future__ import annotations

from typing import Any, NamedTuple

import numpy as np

from opti_mind.config import get_settings
from opti_mind.modeling.ir_models import IRModel, IRVariable
from opti_mind.solver.backends.base import SolverBackend
from opti_mind.solver.compiler import IRToModelCompiler

try:
    import highspy

    _HIGHSPY_AVAILABLE = True
except Exception:  # pragma: no cover - defensive import
    highspy = None  # type: ignore[assignment]
    _HIGHSPY_AVAILABLE = False


class _ColumnInfo(NamedTuple):
    """Metadata for a single HiGHS column."""

    col: int
    key: Any
    domain: str


class _ResolvedRhs:
    """Resolved right-hand side of a constraint.

    Tracks whether the RHS is a variable reference (which must be moved to the
    left-hand side), a parameter dictionary, a scalar literal, or missing.
    """

    def __init__(
        self,
        variable: int | dict[Any, int] | None = None,
        parameter: dict[Any, float] | None = None,
        scalar: float | None = None,
    ) -> None:
        self.variable = variable
        self.parameter = parameter
        self.scalar = scalar

    def resolve_value(self, key: Any) -> float:
        """Return the scalar RHS value for the given index key."""
        if self.scalar is not None:
            return float(self.scalar)
        if self.parameter is not None:
            return float(self.parameter.get(key, 0.0))
        if self.variable is not None:
            # Variable RHS is moved to LHS; bound is zero.
            return 0.0
        return 0.0

    def variable_column(self, key: Any) -> int | None:
        """Return the column index to subtract when RHS is a variable."""
        if self.variable is None:
            return None
        if isinstance(self.variable, dict):
            return self.variable.get(key)
        return self.variable


class _RowBuilder:
    """Accumulates rows for the HiGHS constraint matrix."""

    def __init__(self) -> None:
        self._cols: list[list[int]] = []
        self._coefs: list[list[float]] = []
        self._lower: list[float] = []
        self._upper: list[float] = []

    def add_row(
        self,
        cols: list[int],
        coefs: list[float],
        lower: float,
        upper: float,
    ) -> None:
        """Add a row with coefficient list and bounds."""
        self._cols.append(cols)
        self._coefs.append(coefs)
        self._lower.append(lower)
        self._upper.append(upper)

    @property
    def num_rows(self) -> int:
        return len(self._cols)

    def build_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """Return row_lower and row_upper arrays."""
        lower = np.array(self._lower, dtype=np.float64)
        upper = np.array(self._upper, dtype=np.float64)
        return lower, upper

    def build_csc(
        self,
        num_cols: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Build CSC sparse matrix arrays from accumulated rows."""
        entries: list[list[tuple[int, float]]] = [[] for _ in range(num_cols)]
        for row_idx, (cols, coefs) in enumerate(zip(self._cols, self._coefs, strict=True)):
            for col, coef in zip(cols, coefs, strict=True):
                entries[col].append((row_idx, coef))

        start: list[int] = [0]
        index: list[int] = []
        value: list[float] = []
        for col_entries in entries:
            index.extend(row for row, _ in col_entries)
            value.extend(coef for _, coef in col_entries)
            start.append(len(index))

        start_arr = np.array(start, dtype=np.int32)
        index_arr = np.array(index, dtype=np.int32)
        value_arr = np.array(value, dtype=np.float64)
        return start_arr, index_arr, value_arr


class IRToHighsCompiler:
    """Compiles an IRModel into a highspy HighsLp."""

    def compile(self, ir: IRModel) -> tuple[Any, dict[str, Any], dict[str, int]]:
        """Build a HiGHS LP/MIP model from IR.

        Returns:
            (lp, var_index, constraint_index) where ``var_index`` maps IR
            variable names to column indices and ``constraint_index`` maps an
            expanded constraint identifier (``name`` for scalar constraints,
            ``name_key`` for indexed constraints) to its HiGHS row index.

        """
        if not _HIGHSPY_AVAILABLE or highspy is None:
            raise RuntimeError("highspy is not installed")

        set_members = IRToModelCompiler._build_set_members(ir)
        arc_lookup = IRToModelCompiler._build_arc_lookup(ir.sets, set_members)
        params = IRToModelCompiler._build_params(ir)
        var_defs = {v.name: v for v in ir.variables}

        var_infos = self._collect_variables(ir, set_members)

        # Assign sequential column indices.
        col_counter = 0
        for name, info in var_infos.items():
            if isinstance(info, dict):
                for key in list(info.keys()):
                    info[key] = info[key]._replace(col=col_counter)
                    col_counter += 1
            else:
                var_infos[name] = info._replace(col=col_counter)
                col_counter += 1

        var_index = self._build_var_index(var_infos)
        num_cols = col_counter

        domains: list[str] = ["continuous"] * num_cols
        lowers: list[float] = [0.0] * num_cols
        uppers: list[float] = [highspy.kHighsInf] * num_cols
        for name, info in var_infos.items():
            entries = info.values() if isinstance(info, dict) else [info]
            for ci in entries:
                var_def = next(v for v in ir.variables if v.name == name)
                domains[ci.col] = ci.domain
                lowers[ci.col] = self._domain_lower(ci.domain, var_def.lower)
                uppers[ci.col] = self._domain_upper(ci.domain, var_def.upper)

        col_cost = np.zeros(num_cols, dtype=np.float64)
        if ir.objective:
            for term in ir.objective.terms:
                self._add_objective_term(term, var_index, col_cost, params)

        row_builder = _RowBuilder()
        constraint_index: dict[str, int] = {}
        for constraint in ir.constraints:
            self._add_constraint(
                constraint,
                var_index,
                var_defs,
                set_members,
                params,
                arc_lookup,
                row_builder,
                constraint_index,
            )

        lp = highspy.HighsLp()
        lp.num_col_ = num_cols
        lp.num_row_ = row_builder.num_rows
        lp.sense_ = (
            highspy.ObjSense.kMaximize if ir.sense == "maximize" else highspy.ObjSense.kMinimize
        )
        lp.col_cost_ = col_cost
        lp.col_lower_ = np.array(lowers, dtype=np.float64)
        lp.col_upper_ = np.array(uppers, dtype=np.float64)
        if row_builder.num_rows > 0:
            lp.row_lower_, lp.row_upper_ = row_builder.build_bounds()
        else:
            lp.row_lower_ = np.array([], dtype=np.float64)
            lp.row_upper_ = np.array([], dtype=np.float64)

        if num_cols > 0:
            (
                lp.a_matrix_.start_,
                lp.a_matrix_.index_,
                lp.a_matrix_.value_,
            ) = row_builder.build_csc(num_cols)

        if num_cols > 0 and any(d in ("binary", "integer") for d in domains):
            lp.integrality_ = np.array(  # type: ignore[assignment]
                [
                    (
                        highspy.HighsVarType.kInteger
                        if d in ("binary", "integer")
                        else highspy.HighsVarType.kContinuous
                    )
                    for d in domains
                ],
                dtype=highspy.HighsVarType,
            )

        return lp, var_index, constraint_index

    def _collect_variables(
        self,
        ir: IRModel,
        set_members: dict[str, list[Any]],
    ) -> dict[str, _ColumnInfo | dict[Any, _ColumnInfo]]:
        """Collect column metadata for every IR variable."""
        var_infos: dict[str, _ColumnInfo | dict[Any, _ColumnInfo]] = {}
        for var_def in ir.variables:
            info = self._declare_variable(var_def, set_members)
            var_infos[var_def.name] = info
        return var_infos

    def _build_var_index(
        self,
        var_infos: dict[str, _ColumnInfo | dict[Any, _ColumnInfo]],
    ) -> dict[str, Any]:
        """Build the consumer-facing var_index from column metadata."""
        var_index: dict[str, Any] = {}
        for name, info in var_infos.items():
            if isinstance(info, dict):
                var_index[name] = {ci.key: ci.col for ci in info.values()}
            else:
                var_index[name] = info.col
        return var_index

    def _declare_variable(
        self,
        var_def: IRVariable,
        set_members: dict[str, list[Any]],
    ) -> _ColumnInfo | dict[Any, _ColumnInfo]:
        """Create column metadata for a scalar or indexed variable."""
        domain = var_def.domain
        if not var_def.sets:
            return _ColumnInfo(col=-1, key=(), domain=domain)

        indices = IRToModelCompiler._cartesian(
            [set_members.get(s, list(range(3))) for s in var_def.sets]
        )
        info_dict: dict[Any, _ColumnInfo] = {}
        for idx_tuple in indices:
            key = idx_tuple[0] if len(idx_tuple) == 1 else idx_tuple
            info_dict[key] = _ColumnInfo(col=-1, key=key, domain=domain)
        return info_dict

    @staticmethod
    def _domain_lower(domain: str, lower: float | None) -> float:
        if domain == "binary":
            return 0.0
        return lower if lower is not None else 0.0

    @staticmethod
    def _domain_upper(domain: str, upper: float | None) -> float:
        if domain == "binary":
            return 1.0
        if upper is None:
            return highspy.kHighsInf
        return upper

    def _add_objective_term(
        self,
        term: Any,
        var_index: dict[str, Any],
        col_cost: np.ndarray,
        params: dict[str, Any],
    ) -> None:
        """Add a single objective term to the cost vector."""
        var_obj = var_index.get(term.var)
        if var_obj is None:
            return

        if isinstance(var_obj, dict):
            for key, col in var_obj.items():
                indices = (key,) if not isinstance(key, tuple) else key
                coef = IRToModelCompiler._eval_coef(term.coef, indices, params)
                col_cost[col] += coef
        else:
            coef = IRToModelCompiler._eval_coef(term.coef, (), params)
            col_cost[var_obj] += coef

    def _add_constraint(
        self,
        constraint: Any,
        var_index: dict[str, Any],
        var_defs: dict[str, IRVariable],
        set_members: dict[str, list[Any]],
        params: dict[str, Any],
        arc_lookup: dict[str, dict[str, Any]],
        rows: _RowBuilder,
        constraint_index: dict[str, int],
    ) -> None:
        """Add a constraint to the row builder using generic scope parsing."""
        for row_key, entries, rhs_constant in IRToModelCompiler._compile_constraint_rows(
            constraint, var_defs, set_members, params, arc_lookup
        ):
            if not entries:
                continue
            cols: list[int] = []
            coefs: list[float] = []
            for var_name, var_key, coef in entries:
                var_obj = var_index.get(var_name)
                if var_obj is None:
                    continue
                if isinstance(var_obj, dict):
                    col = var_obj.get(var_key)
                    if col is None:
                        continue
                else:
                    col = var_obj
                cols.append(col)
                coefs.append(coef)
            lb, ub = self._sense_to_bounds(constraint.sense, rhs_constant)
            constraint_index[self._constraint_id(constraint.name, row_key)] = rows.num_rows
            rows.add_row(cols, coefs, lb, ub)

    def _resolve_rhs(
        self,
        rhs: Any,
        var_index: dict[str, Any],
        params: dict[str, Any],
    ) -> _ResolvedRhs:
        """Resolve RHS into a variable column reference or scalar value."""
        var_obj = var_index.get(rhs)
        if var_obj is not None:
            return _ResolvedRhs(variable=var_obj)

        try:
            return _ResolvedRhs(scalar=float(rhs))
        except (ValueError, TypeError):
            pass

        param = params.get(rhs)
        if param is not None:
            if isinstance(param, dict):
                return _ResolvedRhs(parameter=param)
            return _ResolvedRhs(scalar=float(param))

        return _ResolvedRhs()

    @staticmethod
    def _infer_scope_index(scope: str) -> int:
        """Infer which variable index the scope quantifies over.

        Mirrors the heuristic used by IRToModelCompiler so that HiGHS and
        CPLEX backends expand summed constraints identically.
        """
        if "j in J" in scope and "i in I" not in scope:
            return 1
        return 0

    @staticmethod
    def _constraint_id(name: str, key: Any) -> str:
        """Build an expanded constraint identifier.

        Scalar constraints use ``name``; indexed constraints use
        ``name_<key>`` so each generated row can be addressed individually.
        """
        if key is None:
            return name
        key_str = "_".join(str(k) for k in key) if isinstance(key, tuple) else str(key)
        return f"{name}_{key_str}"

    def _sense_to_bounds(
        self,
        sense: str,
        rhs: float,
    ) -> tuple[float, float]:
        """Convert a constraint sense and scalar RHS into HiGHS row bounds."""
        inf = highspy.kHighsInf
        if sense == "eq":
            return float(rhs), float(rhs)
        if sense == "le":
            return -inf, float(rhs)
        if sense == "ge":
            return float(rhs), inf
        # Fallback to <=
        return -inf, float(rhs)


class HighsBackend(SolverBackend):
    """Solve an IR using the HiGHS open-source MILP solver."""

    name = "highs"

    @classmethod
    def available(cls) -> bool:
        """Check that highspy is importable and functional."""
        if not _HIGHSPY_AVAILABLE or highspy is None:
            return False
        try:
            h = highspy.Highs()  # type: ignore[no-untyped-call]
            return h.getModelStatus() is not None
        except Exception:
            return False

    def solve(self, ir: IRModel) -> dict[str, Any]:
        """Compile IR to a HighsLp, solve, and extract the solution.

        In addition to primal values, HiGHS provides row and column duals which
        are returned as ``dual_values`` and ``reduced_costs`` respectively.
        """
        compiler = IRToHighsCompiler()
        lp, var_index, constraint_index = compiler.compile(ir)

        h = highspy.Highs()  # type: ignore[no-untyped-call]
        settings = get_settings()
        h.setOptionValue("time_limit", float(settings.solver_timeout))

        h.passModel(lp)
        h.run()

        model_status = h.getModelStatus()
        info = h.getInfo()

        is_optimal = model_status == highspy.HighsModelStatus.kOptimal
        has_feasible = info.primal_solution_status == highspy.kSolutionStatusFeasible

        if not is_optimal and not has_feasible:
            return {
                "status": "no_solution",
                "objective_value": None,
                "variables": {},
                "dual_values": None,
                "reduced_costs": None,
                "constraint_values": None,
            }

        solution = h.getSolution()
        col_values = list(solution.col_value)
        col_duals = list(solution.col_dual)
        row_duals = list(solution.row_dual)
        row_values = list(solution.row_value)

        var_values: dict[str, Any] = {}
        reduced_costs: dict[str, Any] = {}
        for name, obj in var_index.items():
            if isinstance(obj, dict):
                var_values[name] = {}
                reduced_costs[name] = {}
                for key, col in obj.items():
                    key_str = "_".join(str(k) for k in key) if isinstance(key, tuple) else str(key)
                    var_values[name][key_str] = col_values[col]
                    reduced_costs[name][key_str] = col_duals[col]
            else:
                var_values[name] = col_values[obj]
                reduced_costs[name] = col_duals[obj]

        dual_values = {cid: row_duals[row] for cid, row in constraint_index.items()}
        constraint_values = {cid: row_values[row] for cid, row in constraint_index.items()}

        status = "optimal" if is_optimal else "feasible"
        return {
            "status": status,
            "objective_value": info.objective_function_value,
            "variables": var_values,
            "dual_values": dual_values,
            "reduced_costs": reduced_costs,
            "constraint_values": constraint_values,
        }

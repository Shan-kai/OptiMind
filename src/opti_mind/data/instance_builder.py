"""Instance Builder: assemble an OptimizationInstance from mapped features.

Supports multiple problem types via heuristic column-pattern detection:
  facility_location, assignment, transportation, knapsack, scheduling,
  inventory and network_flow.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

import pandas as pd

from opti_mind.data.keyword_mapping import get_canonical_role_for_semantic_role
from opti_mind.data.models import CanonicalRole, FieldSemantics, OptimizationInstance


class _ProblemSignature(NamedTuple):
    """Heuristic signature used to detect a problem type from column semantics."""

    problem_type: str
    index_roles: list[str]
    required_roles: set[CanonicalRole]
    optional_roles: set[CanonicalRole]


# Problem-type signatures used for detection.  Order matters: more specific
# combinations (e.g. knapsack) are checked before generic ones.
_PROBLEM_SIGNATURES: list[_ProblemSignature] = [
    _ProblemSignature(
        problem_type="knapsack",
        index_roles=["item"],
        required_roles={CanonicalRole.VALUE, CanonicalRole.WEIGHT},
        optional_roles={CanonicalRole.CAPACITY},
    ),
    _ProblemSignature(
        problem_type="scheduling",
        index_roles=["job"],
        required_roles={CanonicalRole.PROCESSING_TIME},
        optional_roles={CanonicalRole.DUE_DATE, CanonicalRole.WEIGHT},
    ),
    _ProblemSignature(
        problem_type="inventory",
        index_roles=["item", "period"],
        required_roles={CanonicalRole.DEMAND, CanonicalRole.HOLDING_COST},
        optional_roles={
            CanonicalRole.ORDERING_COST,
            CanonicalRole.PURCHASE_COST,
            CanonicalRole.INITIAL_INVENTORY,
        },
    ),
    _ProblemSignature(
        problem_type="facility_location",
        index_roles=["customer", "facility"],
        required_roles={CanonicalRole.CUSTOMER_KEY, CanonicalRole.FACILITY_KEY},
        optional_roles={
            CanonicalRole.DEMAND,
            CanonicalRole.CAPACITY,
            CanonicalRole.FIXED_COST,
            CanonicalRole.COST,
            CanonicalRole.DISTANCE,
        },
    ),
    _ProblemSignature(
        problem_type="assignment",
        index_roles=["agent", "task"],
        required_roles={CanonicalRole.AGENT_KEY, CanonicalRole.TASK_KEY, CanonicalRole.COST},
        optional_roles=set(),
    ),
    _ProblemSignature(
        problem_type="transportation",
        index_roles=["source", "sink"],
        required_roles={
            CanonicalRole.SOURCE_KEY,
            CanonicalRole.SINK_KEY,
            CanonicalRole.SUPPLY,
            CanonicalRole.DEMAND,
        },
        optional_roles={CanonicalRole.COST, CanonicalRole.DISTANCE},
    ),
    _ProblemSignature(
        problem_type="network_flow",
        index_roles=["node"],
        required_roles={CanonicalRole.COST, CanonicalRole.CAPACITY},
        optional_roles={CanonicalRole.BALANCE},
    ),
]


class GenericInstanceBuilder:
    """Build an OptimizationInstance from mapped features.

    Supports multiple problem types by detecting index columns (e.g.
    customer/facility, agent/task, source/sink, item, job) in the semantics.
    """

    def build(
        self,
        mapped: dict[CanonicalRole, pd.Series],
        df: pd.DataFrame,
        semantics: list[FieldSemantics],
        dataset_id: str | None = None,
        problem_type: str | None = None,
    ) -> OptimizationInstance:
        """Build an OptimizationInstance from mapped features.

        Args:
            problem_type: Optional user-selected problem type. When provided and
                the data contains the required roles, it overrides auto-detection.
        """
        detected_type, index_roles = self._detect_problem_type(semantics, hint=problem_type)

        if detected_type == "knapsack":
            return self._build_knapsack(mapped, df, semantics, dataset_id=dataset_id)
        if detected_type == "scheduling":
            return self._build_scheduling(mapped, df, semantics, dataset_id=dataset_id)
        if detected_type == "inventory":
            return self._build_inventory(mapped, df, semantics, dataset_id=dataset_id)
        if detected_type == "network_flow":
            return self._build_network_flow(mapped, df, semantics, dataset_id=dataset_id)

        return self._build_two_index_problem(
            detected_type,
            index_roles,
            mapped,
            df,
            semantics,
            dataset_id=dataset_id,
        )

    def _build_knapsack(
        self,
        mapped: dict[CanonicalRole, pd.Series],
        df: pd.DataFrame,
        semantics: list[FieldSemantics],
        dataset_id: str | None = None,
    ) -> OptimizationInstance:
        """Build a 0/1 knapsack OptimizationInstance."""
        item_col = self._find_semantic_column(semantics, "item")
        if item_col and item_col in df.columns:
            items = sorted(str(v) for v in df[item_col].unique() if pd.notna(v))
        else:
            items = [str(i) for i in range(len(df))]

        value_series = self._get_mapped_series(mapped, CanonicalRole.VALUE)
        weight_series = self._get_mapped_series(mapped, CanonicalRole.WEIGHT)
        capacity_series = self._get_mapped_series(mapped, CanonicalRole.CAPACITY)

        parameters: dict[str, Any] = {}
        if value_series is not None:
            parameters["v"] = self._to_dict_by_index(value_series, df, item_col, items)
        if weight_series is not None:
            parameters["w"] = self._to_dict_by_index(weight_series, df, item_col, items)
        if capacity_series is not None:
            # Capacity is a scalar constant; take the first non-missing value.
            parameters["C"] = float(capacity_series.dropna().iloc[0])

        return OptimizationInstance(
            problem_type="knapsack",
            sets={"I": items},
            parameters=parameters,
            meta={
                "dataset_id": dataset_id,
                "fields": [s.model_dump() for s in semantics],
            },
        )

    def _build_scheduling(
        self,
        mapped: dict[CanonicalRole, pd.Series],
        df: pd.DataFrame,
        semantics: list[FieldSemantics],
        dataset_id: str | None = None,
    ) -> OptimizationInstance:
        """Build a single-machine scheduling OptimizationInstance.

        The continuous-time ontology only needs the job set J and per-job
        parameters p_j (processing time) and w_j (weight).  A period/time-grid
        set is no longer required.
        """
        job_col = self._find_semantic_column(semantics, "job")
        if job_col and job_col in df.columns:
            jobs = sorted(str(v) for v in df[job_col].unique() if pd.notna(v))
        else:
            jobs = [str(i) for i in range(len(df))]

        parameters: dict[str, Any] = {}
        pt = self._get_mapped_series(mapped, CanonicalRole.PROCESSING_TIME)
        dd = self._get_mapped_series(mapped, CanonicalRole.DUE_DATE)
        wt = self._get_mapped_series(mapped, CanonicalRole.WEIGHT)
        if pt is not None:
            parameters["p"] = self._to_dict_by_index(pt, df, job_col, jobs)
            # Compute a big-M for the disjunctive constraints from total
            # processing time.
            with contextlib.suppress(Exception):
                parameters["M"] = sum(float(v) for v in parameters["p"].values())
        if dd is not None:
            parameters["d"] = self._to_dict_by_index(dd, df, job_col, jobs)
        if wt is not None:
            parameters["w"] = self._to_dict_by_index(wt, df, job_col, jobs)

        return OptimizationInstance(
            problem_type="scheduling",
            sets={"J": jobs},
            parameters=parameters,
            meta={
                "dataset_id": dataset_id,
                "fields": [s.model_dump() for s in semantics],
            },
        )

    def _build_inventory(
        self,
        mapped: dict[CanonicalRole, pd.Series],
        df: pd.DataFrame,
        semantics: list[FieldSemantics],
        dataset_id: str | None = None,
    ) -> OptimizationInstance:
        """Build a multi-period inventory OptimizationInstance."""
        item_col = self._find_semantic_column(semantics, "item")
        period_col = self._find_semantic_column(semantics, "period")

        if item_col and item_col in df.columns:
            items = sorted(str(v) for v in df[item_col].unique() if pd.notna(v))
        else:
            items = [str(i) for i in range(len(df))]

        if period_col and period_col in df.columns:
            periods = sorted(str(v) for v in df[period_col].unique() if pd.notna(v))
        else:
            periods = [str(i) for i in range(len(df))]

        parameters: dict[str, Any] = {}

        demand_series = self._get_mapped_series(mapped, CanonicalRole.DEMAND)
        if demand_series is not None and item_col and period_col:
            parameters["d"] = self._to_nested_dict(
                demand_series, df, item_col, period_col, items, periods
            )
            # Compute a conservative big-M for the order-placement linking
            # constraint from total per-item demand.
            with contextlib.suppress(Exception):
                parameters["M"] = max(
                    sum(float(v) for v in item_demands.values())
                    for item_demands in parameters["d"].values()
                )

        for role, param in [
            (CanonicalRole.HOLDING_COST, "h"),
            (CanonicalRole.ORDERING_COST, "s"),
            (CanonicalRole.PURCHASE_COST, "c"),
            (CanonicalRole.INITIAL_INVENTORY, "I0"),
        ]:
            series = self._get_mapped_series(mapped, role)
            if series is not None:
                parameters[param] = self._to_dict_by_index(series, df, item_col, items)

        return OptimizationInstance(
            problem_type="inventory",
            sets={"I": items, "T": periods},
            parameters=parameters,
            meta={
                "dataset_id": dataset_id,
                "fields": [s.model_dump() for s in semantics],
            },
        )

    def _build_network_flow(
        self,
        mapped: dict[CanonicalRole, pd.Series],
        df: pd.DataFrame,
        semantics: list[FieldSemantics],
        dataset_id: str | None = None,
    ) -> OptimizationInstance:
        """Build a minimum-cost network-flow OptimizationInstance.

        Expects an arc list with source/target nodes, cost and capacity.  Set N
        is inferred from all node identifiers appearing in the arc list.  Node
        balances (``b_i``) may be supplied as additional rows where ``node2`` is
        empty and a ``balance`` column gives the supply (+) or demand (-).
        """
        node1_col = self._find_semantic_column(semantics, "source") or self._find_column(
            semantics, "node1"
        )
        node2_col = self._find_semantic_column(semantics, "sink") or self._find_column(
            semantics, "node2"
        )
        if not node1_col or not node2_col:
            node1_col = df.columns[0]
            node2_col = df.columns[1]

        arcs: list[list[str]] = []
        nodes: set[str] = set()
        balance_by_node: dict[str, float] = {}
        for _idx, row in df.iterrows():
            n1 = str(row[node1_col])
            n2 = row[node2_col]
            if pd.isna(n2) or str(n2).strip() == "":
                # Node attribute row: used for supply/demand balance.
                nodes.add(n1)
                balance_col = self._find_canonical_column_by_role(semantics, CanonicalRole.BALANCE)
                if balance_col and balance_col in df.columns and pd.notna(row[balance_col]):
                    balance_by_node[n1] = float(row[balance_col])
                continue
            n2 = str(n2)
            arcs.append([n1, n2])
            nodes.update([n1, n2])

        cost_series = self._get_mapped_series(mapped, {CanonicalRole.COST, CanonicalRole.DISTANCE})
        capacity_series = self._get_mapped_series(mapped, CanonicalRole.CAPACITY)
        balance_series = self._get_mapped_series(mapped, CanonicalRole.BALANCE)

        parameters: dict[str, Any] = {}
        if cost_series is not None:
            parameters["c"] = {
                f"{a[0]}_{a[1]}": float(v)
                for a, (_, v) in zip(arcs, cost_series.dropna().items(), strict=False)
            }
        if capacity_series is not None:
            parameters["u"] = {
                f"{a[0]}_{a[1]}": float(v)
                for a, (_, v) in zip(arcs, capacity_series.dropna().items(), strict=False)
            }
        if balance_by_node or balance_series is not None:
            if balance_by_node:
                parameters["b"] = balance_by_node
            elif balance_series is not None:
                parameters["b"] = {
                    str(n): float(v)
                    for n, (_, v) in zip(nodes, balance_series.items(), strict=False)
                    if pd.notna(v)
                }

        return OptimizationInstance(
            problem_type="network_flow",
            sets={"N": sorted(nodes), "A": [f"{a[0]}_{a[1]}" for a in arcs]},
            parameters=parameters,
            meta={
                "dataset_id": dataset_id,
                "fields": [s.model_dump() for s in semantics],
            },
        )

    def _build_two_index_problem(
        self,
        problem_type: str,
        index_roles: list[str],
        mapped: dict[CanonicalRole, pd.Series],
        df: pd.DataFrame,
        semantics: list[FieldSemantics],
        dataset_id: str | None = None,
    ) -> OptimizationInstance:
        """Build facility_location / assignment / transportation instances."""
        set_names: list[str] = ["I", "J"]

        sets_dict: dict[str, list[str]] = {}
        for set_name, idx_role in zip(set_names, index_roles, strict=False):
            canonical_role = get_canonical_role_for_semantic_role(idx_role)
            col = (
                self._find_canonical_column_by_role(semantics, canonical_role)
                if canonical_role is not None
                else None
            )
            if col and col in df.columns:
                sets_dict[set_name] = sorted(str(v) for v in df[col].unique() if pd.notna(v))
            else:
                sets_dict[set_name] = []

        cost_series = self._get_mapped_series(mapped, {CanonicalRole.COST, CanonicalRole.DISTANCE})
        cost_matrix = None
        if cost_series is not None:
            cost_matrix = self._build_cost_matrix(cost_series, df, semantics, index_roles)

        if not sets_dict["I"] and cost_matrix is not None:
            sets_dict["I"] = sorted(cost_matrix.keys())
        if not sets_dict["J"] and cost_matrix is not None:
            sets_dict["J"] = sorted({f for row in cost_matrix.values() for f in row})
        if not sets_dict["I"]:
            sets_dict["I"] = self._index_list(mapped, CanonicalRole.DEMAND)
        if not sets_dict["J"]:
            sets_dict["J"] = self._index_list(
                mapped, CanonicalRole.CAPACITY, alt=CanonicalRole.FIXED_COST
            )

        # Map base parameter names to the index role they belong to (0 = first
        # index column, 1 = second index column).  None means cost-matrix style
        # (uses both index sets).
        param_index_role: Mapping[str, int | None] = {
            "facility_location": {"d": 0, "Q": 1, "f": 1},
            "assignment": {},
            "transportation": {"s": 0, "d": 1},
        }.get(problem_type) or {}

        parameters: dict[str, object] = {}

        demand_series = self._get_mapped_series(mapped, CanonicalRole.DEMAND)
        if demand_series is not None:
            idx = param_index_role.get("d", 0)
            if idx is not None:
                role = index_roles[idx]
                target_set = sets_dict[["I", "J"][idx]]
                parameters["d"] = self._deduplicate_by_column(
                    demand_series, df, semantics, role, target_set
                )

        supply_series = self._get_mapped_series(mapped, CanonicalRole.SUPPLY)
        if supply_series is not None:
            idx = param_index_role.get("s", 0)
            if idx is not None:
                role = index_roles[idx]
                target_set = sets_dict[["I", "J"][idx]]
                parameters["s"] = self._deduplicate_by_column(
                    supply_series, df, semantics, role, target_set
                )

        capacity_series = self._get_mapped_series(mapped, CanonicalRole.CAPACITY)
        if capacity_series is not None:
            idx = param_index_role.get("Q", 1)
            if idx is not None:
                role = index_roles[idx]
                target_set = sets_dict[["I", "J"][idx]]
                parameters["Q"] = self._deduplicate_by_column(
                    capacity_series, df, semantics, role, target_set
                )

        fixed_cost_series = self._get_mapped_series(mapped, CanonicalRole.FIXED_COST)
        if fixed_cost_series is not None:
            idx = param_index_role.get("f", 1)
            if idx is not None:
                role = index_roles[idx]
                target_set = sets_dict[["I", "J"][idx]]
                parameters["f"] = self._deduplicate_by_column(
                    fixed_cost_series, df, semantics, role, target_set
                )

        if cost_matrix is not None:
            parameters["c"] = cost_matrix

        return OptimizationInstance(
            problem_type=problem_type,
            sets=sets_dict,
            parameters=parameters,
            meta={
                "dataset_id": dataset_id,
                "fields": [s.model_dump() for s in semantics],
            },
        )

    def _detect_problem_type(
        self,
        semantics: list[FieldSemantics],
        hint: str | None = None,
    ) -> tuple[str, list[str]]:
        """Detect problem type and index roles from semantics.

        Scores each signature by how many of its required roles are present.
        The signature with the highest score wins; ties are broken by order.

        If ``hint`` matches a known signature and the data has at least one
        required role for that signature, the hint is preferred.  This lets
        users override auto-detection while still validating that the data is
        plausibly compatible.
        """
        roles = {s.canonical_role for s in semantics if s.canonical_role}
        column_names = {s.column.lower() for s in semantics}
        best_score = -1
        best_signature: _ProblemSignature | None = None

        # If a hint is provided, boost its signature so it wins when plausible.
        hint_signature: _ProblemSignature | None = None
        if hint:
            for signature in _PROBLEM_SIGNATURES:
                if signature.problem_type == hint:
                    hint_signature = signature
                    break

        for signature in _PROBLEM_SIGNATURES:
            matched_required = len(roles & signature.required_roles)
            matched_optional = len(roles & signature.optional_roles)
            # Full required match dominates; partial required matches are weaker
            # than strong optional matches, so that degenerate facility-location
            # data (demand + capacity without index columns) still defaults to
            # facility_location rather than inventory.
            if matched_required == len(signature.required_roles):
                score = matched_required * 2 + matched_optional
            elif matched_required > 0:
                score = matched_required
            else:
                score = matched_optional

            # Fallback: if canonical roles are missing (e.g. an LLM returned
            # unfamiliar roles), use literal column-name keywords.
            if score == 0:
                score = self._keyword_score(signature, column_names)

            if hint_signature is signature and matched_required > 0:
                # Prefer the user's hint as long as the data looks compatible.
                score += 100

            if score > best_score:
                best_score = score
                best_signature = signature

        if best_signature is not None:
            return best_signature.problem_type, list(best_signature.index_roles)

        return "facility_location", ["customer", "facility"]

    @staticmethod
    def _keyword_score(signature: _ProblemSignature, column_names: set[str]) -> int:
        """Return a heuristic score based on literal column-name keywords."""
        keyword_map: dict[str, set[str]] = {
            "knapsack": {"value", "weight", "profit", "benefit", "capacity"},
            "scheduling": {"job", "processing_time", "due_date", "deadline"},
            "inventory": {"period", "holding_cost", "ordering_cost", "initial_inventory"},
            "facility_location": {"customer", "facility", "fixed_cost", "transport_cost"},
            "assignment": {"agent", "task", "cost"},
            "transportation": {"source", "sink", "supply", "demand"},
            "network_flow": {"node", "arc", "cost", "capacity"},
        }
        keywords = keyword_map.get(signature.problem_type, set())
        return sum(1 for kw in keywords if any(kw in col for col in column_names))

    def _deduplicate_by_column(
        self,
        series: pd.Series,
        df: pd.DataFrame,
        semantics: list[FieldSemantics],
        role: str,
        expected_keys: Sequence[str],
    ) -> dict[str, float]:
        """Aggregate a repeated long-table column into one value per key."""
        col = self._find_semantic_column(semantics, role)
        if col and col in df.columns:
            grouped: dict[str, float] = {}
            for idx, value in series.dropna().items():
                key = str(df.at[idx, col])
                if key not in grouped:
                    grouped[key] = float(value)
            return {str(k): grouped.get(str(k), 0.0) for k in expected_keys}
        return self._to_dict(series)

    def _find_semantic_column(self, semantics: list[FieldSemantics], role: str) -> str | None:
        """Return the original column name for a given semantic role."""
        canonical = get_canonical_role_for_semantic_role(role)
        if canonical is not None:
            for sem in semantics:
                if sem.canonical_role == canonical:
                    return sem.column
        for sem in semantics:
            if sem.semantic_role == role:
                return sem.column
        for sem in semantics:
            if sem.column.lower() == role:
                return sem.column
        return None

    def _find_column(self, semantics: list[FieldSemantics], name: str) -> str | None:
        """Return a column whose name matches ``name`` literally."""
        for sem in semantics:
            if sem.column.lower() == name.lower():
                return sem.column
        return None

    @staticmethod
    def _find_canonical_column_by_role(
        semantics: list[FieldSemantics], role: CanonicalRole
    ) -> str | None:
        for sem in semantics:
            if sem.canonical_role == role:
                return sem.column
        return None

    @staticmethod
    def _get_mapped_series(
        mapped: dict[CanonicalRole, pd.Series],
        role: CanonicalRole | set[CanonicalRole],
    ) -> pd.Series | None:
        """Return the raw series for a given canonical role (or set of roles)."""
        roles = role if isinstance(role, set) else {role}
        for r in roles:
            series = mapped.get(r)
            if series is not None:
                return series
        return None

    def _build_cost_matrix(
        self,
        cost_series: pd.Series,
        df: pd.DataFrame,
        semantics: list[FieldSemantics],
        index_roles: list[str],
    ) -> dict[str, dict[str, float]] | None:
        """Convert a cost Series into a row x column matrix."""
        if isinstance(cost_series, pd.DataFrame):
            return self._frame_to_dict(cost_series)

        row_role, col_role = index_roles
        row_col = self._find_semantic_column(semantics, row_role)
        col_col = self._find_semantic_column(semantics, col_role)

        if row_col and col_col and row_col in df.columns and col_col in df.columns:
            matrix: dict[str, dict[str, float]] = {}
            for idx, cost in cost_series.dropna().items():
                row_key = str(df.at[idx, row_col])
                col_key = str(df.at[idx, col_col])
                matrix.setdefault(row_key, {})[col_key] = float(cost)
            return matrix

        return None

    @staticmethod
    def _index_list(
        mapped: dict[CanonicalRole, pd.Series],
        primary: CanonicalRole,
        alt: CanonicalRole | None = None,
    ) -> list[str]:
        if primary in mapped:
            return [str(i) for i in mapped[primary].index]
        if alt and alt in mapped:
            return [str(i) for i in mapped[alt].index]
        return []

    @staticmethod
    def _to_dict(series: pd.Series) -> dict[str, float]:
        return {str(i): float(v) for i, v in series.dropna().items()}

    @staticmethod
    def _to_dict_by_index(
        series: pd.Series,
        df: pd.DataFrame,
        index_col: str | None,
        expected_keys: list[str],
    ) -> dict[str, float]:
        """Map a series to a dict keyed by an explicit index column."""
        if index_col and index_col in df.columns:
            grouped: dict[str, float] = {}
            for idx, value in series.dropna().items():
                key = str(df.at[idx, index_col])
                if key not in grouped:
                    grouped[key] = float(value)
            return {str(k): grouped.get(str(k), 0.0) for k in expected_keys}
        return {str(i): float(v) for i, v in series.dropna().items()}

    @staticmethod
    def _to_nested_dict(
        series: pd.Series,
        df: pd.DataFrame,
        row_col: str,
        col_col: str,
        row_keys: list[str],
        col_keys: list[str],
    ) -> dict[str, dict[str, float]]:
        """Map a series to a nested dict keyed by two index columns."""
        grouped: dict[str, dict[str, float]] = {}
        for idx, value in series.dropna().items():
            row_key = str(df.at[idx, row_col])
            col_key = str(df.at[idx, col_col])
            grouped.setdefault(row_key, {})[col_key] = float(value)
        return {
            str(r): {str(c): grouped.get(str(r), {}).get(str(c), 0.0) for c in col_keys}
            for r in row_keys
        }

    @staticmethod
    def _frame_to_dict(value: object) -> object:
        if isinstance(value, pd.DataFrame):
            return {
                str(i): {str(j): float(v) for j, v in row.items() if pd.notna(v)}
                for i, row in value.iterrows()
            }
        return None

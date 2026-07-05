"""Data Profiler: deterministic column-wise statistics."""

from __future__ import annotations

import pandas as pd

from opti_mind.data.models import ColumnProfile, DataProfileReport


class DataProfiler:
    """Build a DataProfileReport without any LLM involvement."""

    def profile(self, df: pd.DataFrame) -> DataProfileReport:
        columns = [self._profile_column(df, name) for name in df.columns]
        return DataProfileReport(n_rows=len(df), n_cols=len(columns), columns=columns)

    @staticmethod
    def _profile_column(df: pd.DataFrame, name: str) -> ColumnProfile:
        series = df[name]
        non_null = int(series.notna().sum())
        missing_rate = float(series.isna().mean()) if len(series) else 0.0
        unique_count = int(series.nunique(dropna=True))
        cardinality = unique_count / non_null if non_null else 0.0
        numeric = pd.api.types.is_numeric_dtype(series)
        quantiles: dict[str, float] = {}
        value_range: tuple[object, object] | None = None
        min_value: object | None = None
        max_value: object | None = None
        if numeric and non_null:
            qpoints = [0.0, 0.25, 0.5, 0.75, 1.0]
            qlabels = ["q0", "q25", "q50", "q75", "q100"]
            qs = series.quantile(qpoints)
            quantiles = {
                label: float(qs.iloc[i]) for i, label in enumerate(qlabels) if pd.notna(qs.iloc[i])
            }
            min_value = float(series.min()) if pd.notna(series.min()) else None
            max_value = float(series.max()) if pd.notna(series.max()) else None
            value_range = (min_value, max_value)
        return ColumnProfile(
            name=name,
            dtype=str(series.dtype),
            missing_rate=round(missing_rate, 6),
            non_null_count=non_null,
            unique_count=unique_count,
            cardinality=round(cardinality, 6),
            min_value=min_value,
            max_value=max_value,
            quantiles=quantiles,
            value_range=value_range,
        )

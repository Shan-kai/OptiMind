"""Data Quality Checker: deterministic validation of common data issues."""

from __future__ import annotations

import pandas as pd

from opti_mind.data.models import QualityIssue, QualityReport

_CHECKED_COORDS = ("lat", "latitude", "lon", "lng", "longitude", "x", "y")


class DataQualityChecker:
    """Detect missing values, outliers, duplicates, invalid coordinates.

    Unit conflict and invalid encoding checks are stubs for future phases.
    """

    def __init__(self, outlier_z: float = 3.0) -> None:
        self.outlier_z = outlier_z

    def check(self, df: pd.DataFrame) -> QualityReport:
        issues: list[QualityIssue] = []
        issues.extend(self._missing(df))
        issues.extend(self._duplicates(df))
        issues.extend(self._outliers(df))
        issues.extend(self._invalid_coords(df))
        return QualityReport(issues=issues, passed=not issues)

    @staticmethod
    def _missing(df: pd.DataFrame) -> list[QualityIssue]:
        out: list[QualityIssue] = []
        for col in df.columns:
            rate = float(df[col].isna().mean())
            if rate > 0:
                out.append(
                    QualityIssue(
                        column=str(col),
                        kind="missing_value",
                        detail=f"missing_rate={rate:.3f}",
                    )
                )
        return out

    @staticmethod
    def _duplicates(df: pd.DataFrame) -> list[QualityIssue]:
        n_dup = int(df.duplicated().sum())
        if n_dup > 0:
            return [
                QualityIssue(column="__row__", kind="duplicate", detail=f"{n_dup} duplicate rows")
            ]
        return []

    def _outliers(self, df: pd.DataFrame) -> list[QualityIssue]:
        out: list[QualityIssue] = []
        for col in df.columns:
            series = df[col]
            if not pd.api.types.is_numeric_dtype(series):
                continue
            std = float(series.std(skipna=True))
            mean = float(series.mean(skipna=True))
            if std == 0 or pd.isna(std):
                continue
            mask = (series - mean).abs() > self.outlier_z * std
            n = int(mask.sum())
            if n > 0:
                out.append(
                    QualityIssue(
                        column=str(col),
                        kind="outlier",
                        detail=f"{n} outliers (|z|>{self.outlier_z})",
                    )
                )
        return out

    @staticmethod
    def _invalid_coords(df: pd.DataFrame) -> list[QualityIssue]:
        out: list[QualityIssue] = []
        for col in df.columns:
            low = str(col).lower().strip()
            if low not in _CHECKED_COORDS:
                continue
            if not pd.api.types.is_numeric_dtype(df[col]):
                out.append(
                    QualityIssue(
                        column=str(col),
                        kind="invalid_coordinate",
                        detail="non-numeric coord",
                    )
                )
                continue
            if low.startswith(("lat", "latitude")):
                bad = ~df[col].between(-90, 90, inclusive="both")
            else:
                bad = ~df[col].between(-180, 180, inclusive="both")
            n = int(bad.sum())
            if n > 0:
                out.append(
                    QualityIssue(
                        column=str(col),
                        kind="invalid_coordinate",
                        detail=f"{n} out-of-range coords",
                    )
                )
        return out

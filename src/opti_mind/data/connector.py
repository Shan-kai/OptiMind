"""Data Connector: ingest CSV / Excel into a normalized pandas DataFrame."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from opti_mind.core.exceptions import OptiMindError


class DataConnector:
    """Read raw files into a normalized DataFrame."""

    SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls"}

    def load(self, source: str) -> pd.DataFrame:
        """Load a single file into a DataFrame.

        Deterministic pipeline stage: no LLM involved.
        """
        path = Path(source)
        if path.suffix.lower() not in self.SUPPORTED_SUFFIXES:
            raise OptiMindError(
                "unsupported_source",
                f"unsupported file type: {path.suffix} "
                f"(expected one of {sorted(self.SUPPORTED_SUFFIXES)})",
                status_code=415,
            )
        if not path.exists():
            raise OptiMindError("source_not_found", f"file not found: {source}", status_code=404)

        df = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_excel(path)
        # Normalize: columns to str, strip whitespace from string cells.
        df.columns = [str(c).strip() for c in df.columns]
        return df

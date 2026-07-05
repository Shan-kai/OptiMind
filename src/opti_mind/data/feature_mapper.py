"""Feature Mapper: project raw columns onto canonical roles."""

from __future__ import annotations

import pandas as pd

from opti_mind.data.models import CanonicalRole, FieldSemantics


class FeatureMapper:
    """Apply FieldSemantics to a DataFrame, producing a canonical_role -> series map."""

    def map(
        self, df: pd.DataFrame, semantics: list[FieldSemantics]
    ) -> dict[CanonicalRole, pd.Series]:
        mapped: dict[CanonicalRole, pd.Series] = {}
        for sem in semantics:
            if (
                sem.canonical_role
                and sem.canonical_role not in (CanonicalRole.IGNORE, CanonicalRole.OTHER)
                and sem.column in df.columns
            ):
                mapped[sem.canonical_role] = df[sem.column]
        return mapped

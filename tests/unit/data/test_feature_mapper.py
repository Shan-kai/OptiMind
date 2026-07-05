"""Tests for FeatureMapper."""

import pandas as pd

from opti_mind.data.feature_mapper import FeatureMapper
from opti_mind.data.models import CanonicalRole, FieldSemantics


def test_maps_by_canonical_role() -> None:
    """FeatureMapper returns series keyed by canonical_role, not optimization_symbol."""
    df = pd.DataFrame(
        {
            "customer": ["C1", "C2"],
            "demand": [10.0, 20.0],
            "cost": [1.0, 2.0],
        }
    )
    semantics = [
        FieldSemantics(column="customer", canonical_role=CanonicalRole.CUSTOMER_KEY),
        FieldSemantics(
            column="demand",
            canonical_role=CanonicalRole.DEMAND,
            optimization_symbol="d_i",
        ),
        FieldSemantics(
            column="cost",
            canonical_role=CanonicalRole.COST,
            optimization_symbol="c_ij",
        ),
    ]

    mapped = FeatureMapper().map(df, semantics)

    assert CanonicalRole.DEMAND in mapped
    assert CanonicalRole.COST in mapped
    assert "d_i" not in mapped
    assert "c_ij" not in mapped
    pd.testing.assert_series_equal(mapped[CanonicalRole.DEMAND], df["demand"])
    pd.testing.assert_series_equal(mapped[CanonicalRole.COST], df["cost"])


def test_ignores_other_and_ignore_roles() -> None:
    """Columns marked IGNORE or OTHER are not included in the mapping."""
    df = pd.DataFrame({"notes": ["a", "b"], "id": [1, 2]})
    semantics = [
        FieldSemantics(column="notes", canonical_role=CanonicalRole.OTHER),
        FieldSemantics(column="id", canonical_role=CanonicalRole.IGNORE),
    ]

    mapped = FeatureMapper().map(df, semantics)

    assert mapped == {}


def test_skips_missing_columns() -> None:
    """Semantics referencing columns not present in the dataframe are skipped."""
    df = pd.DataFrame({"demand": [10.0, 20.0]})
    semantics = [
        FieldSemantics(
            column="missing", canonical_role=CanonicalRole.SUPPLY, optimization_symbol="s_i"
        ),
        FieldSemantics(
            column="demand", canonical_role=CanonicalRole.DEMAND, optimization_symbol="d_i"
        ),
    ]

    mapped = FeatureMapper().map(df, semantics)

    assert CanonicalRole.DEMAND in mapped
    assert CanonicalRole.SUPPLY not in mapped


def test_requires_canonical_role() -> None:
    """Semantics without a canonical_role are not mapped."""
    df = pd.DataFrame({"raw": [1, 2]})
    semantics = [
        FieldSemantics(column="raw", optimization_symbol="x_i"),
    ]

    mapped = FeatureMapper().map(df, semantics)

    assert mapped == {}

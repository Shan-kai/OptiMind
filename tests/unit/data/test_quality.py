import pandas as pd

from opti_mind.data.quality import DataQualityChecker


def test_missing_and_duplicate_detected() -> None:
    df = pd.DataFrame({"demand": [10, 10, None, 40], "x": [1, 1, 3, 4]})
    rep = DataQualityChecker().check(df)
    kinds = {i.kind for i in rep.issues}
    assert "missing_value" in kinds
    assert "duplicate" in kinds
    assert not rep.passed


def test_invalid_latitude_flagged() -> None:
    df = pd.DataFrame({"latitude": [10.0, 95.0, 20.0, -100.0]})
    rep = DataQualityChecker().check(df)
    assert any(i.kind == "invalid_coordinate" for i in rep.issues)

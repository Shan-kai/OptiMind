import pandas as pd

from opti_mind.data.profiler import DataProfiler


def test_profiles_numeric_and_text() -> None:
    df = pd.DataFrame({"demand": [10, 20, None, 40], "name": ["a", "b", "c", "d"]})
    rep = DataProfiler().profile(df)
    assert rep.n_rows == 4
    assert rep.n_cols == 2
    demand = next(c for c in rep.columns if c.name == "demand")
    assert demand.missing_rate == 0.25
    assert "q50" in demand.quantiles
    assert demand.min_value == 10.0

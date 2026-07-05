import pandas as pd

from opti_mind.data.feature_mapper import FeatureMapper
from opti_mind.data.instance_builder import GenericInstanceBuilder
from opti_mind.data.profiler import DataProfiler
from opti_mind.data.schema import HeuristicSchemaInterpreter


def test_builds_facility_location_instance() -> None:
    df = pd.DataFrame(
        {
            "demand": [10, 20, 30],
            "capacity": [100, 120, 90],
            "fixed_cost": [50, 60, 40],
        }
    )
    profile = DataProfiler().profile(df)
    sem = HeuristicSchemaInterpreter().interpret(list(df.columns), profile)
    mapped = FeatureMapper().map(df, sem)
    inst = GenericInstanceBuilder().build(mapped, df, sem, dataset_id="ds")
    assert inst.problem_type == "facility_location"
    assert "I" in inst.sets and "J" in inst.sets
    assert inst.parameters["d"] == {"0": 10.0, "1": 20.0, "2": 30.0}
    assert inst.parameters["Q"]["0"] == 100.0


def test_builds_long_table_with_canonical_role() -> None:
    df = pd.DataFrame(
        {
            "client": ["C1", "C1", "C2", "C2"],
            "warehouse": ["W1", "W2", "W1", "W2"],
            "demand": [10.0, 20.0, 30.0, 40.0],
            "capacity": [100.0, 200.0, 100.0, 200.0],
            "fixed_cost": [50.0, 60.0, 50.0, 60.0],
        }
    )
    profile = DataProfiler().profile(df)
    sem = HeuristicSchemaInterpreter().interpret(list(df.columns), profile)
    mapped = FeatureMapper().map(df, sem)
    inst = GenericInstanceBuilder().build(mapped, df, sem, dataset_id="ds")
    assert inst.problem_type == "facility_location"
    assert inst.sets["I"] == ["C1", "C2"]
    assert inst.sets["J"] == ["W1", "W2"]
    assert inst.parameters["d"] == {"C1": 10.0, "C2": 30.0}
    assert inst.parameters["Q"] == {"W1": 100.0, "W2": 200.0}
    assert inst.parameters["f"] == {"W1": 50.0, "W2": 60.0}


def test_builds_wide_table_with_canonical_role() -> None:
    df = pd.DataFrame(
        {
            "client": ["C1", "C2", "C3"],
            "warehouse": ["W1", "W2", "W3"],
            "demand": [10.0, 20.0, 30.0],
            "capacity": [100.0, 200.0, 300.0],
            "fixed_cost": [50.0, 60.0, 70.0],
        }
    )
    profile = DataProfiler().profile(df)
    sem = HeuristicSchemaInterpreter().interpret(list(df.columns), profile)
    mapped = FeatureMapper().map(df, sem)
    inst = GenericInstanceBuilder().build(mapped, df, sem, dataset_id="ds")
    assert inst.problem_type == "facility_location"
    assert inst.sets["I"] == ["C1", "C2", "C3"]
    assert inst.sets["J"] == ["W1", "W2", "W3"]
    assert inst.parameters["d"] == {"C1": 10.0, "C2": 20.0, "C3": 30.0}
    assert inst.parameters["Q"] == {"W1": 100.0, "W2": 200.0, "W3": 300.0}
    assert inst.parameters["f"] == {"W1": 50.0, "W2": 60.0, "W3": 70.0}


def test_builds_knapsack_instance() -> None:
    df = pd.DataFrame(
        {
            "item": ["i1", "i2", "i3"],
            "value": [5.0, 7.0, 4.0],
            "weight": [2.0, 3.0, 6.0],
            "capacity": [10.0, 10.0, 10.0],
        }
    )
    profile = DataProfiler().profile(df)
    sem = HeuristicSchemaInterpreter().interpret(list(df.columns), profile)
    mapped = FeatureMapper().map(df, sem)
    inst = GenericInstanceBuilder().build(mapped, df, sem, dataset_id="ds")
    assert inst.problem_type == "knapsack"
    assert inst.sets["I"] == ["i1", "i2", "i3"]
    assert inst.parameters["v"] == {"i1": 5.0, "i2": 7.0, "i3": 4.0}
    assert inst.parameters["w"] == {"i1": 2.0, "i2": 3.0, "i3": 6.0}
    assert inst.parameters["C"] == 10.0


def test_builds_scheduling_instance() -> None:
    df = pd.DataFrame(
        {
            "job": ["j1", "j2"],
            "processing_time": [3.0, 2.0],
            "due_date": [5.0, 4.0],
            "weight": [2.0, 3.0],
        }
    )
    profile = DataProfiler().profile(df)
    sem = HeuristicSchemaInterpreter().interpret(list(df.columns), profile)
    mapped = FeatureMapper().map(df, sem)
    inst = GenericInstanceBuilder().build(mapped, df, sem, dataset_id="ds")
    assert inst.problem_type == "scheduling"
    assert inst.sets["J"] == ["j1", "j2"]
    assert inst.parameters["p"] == {"j1": 3.0, "j2": 2.0}
    assert inst.parameters["d"] == {"j1": 5.0, "j2": 4.0}
    assert inst.parameters["w"] == {"j1": 2.0, "j2": 3.0}
    assert inst.parameters.get("M") == 5.0

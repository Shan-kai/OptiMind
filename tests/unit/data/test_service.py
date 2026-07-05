import pandas as pd

from opti_mind.data.service import DataService

FIXTURE = "tests/fixtures/facility_location.csv"


def test_service_builds_instance_from_fixture() -> None:
    inst = DataService().build_instance_from_file(FIXTURE)
    assert inst.problem_type == "facility_location"
    assert inst.meta.get("dataset_id") == "facility_location"
    assert "d" in inst.parameters and "Q" in inst.parameters


def test_service_builds_instance_from_dataframe() -> None:
    df = pd.DataFrame({"demand": [5, 15], "capacity": [50, 60]})
    inst = DataService().build_instance(df, dataset_id="x")
    assert inst.problem_type == "facility_location"
    assert len(inst.sets["I"]) == 2

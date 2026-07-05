import pytest

from opti_mind.core.exceptions import OptiMindError
from opti_mind.data.connector import DataConnector


def test_load_csv(tmp_path) -> None:
    p = tmp_path / "f.csv"
    p.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    df = DataConnector().load(str(p))
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2


def test_unsupported_type(tmp_path) -> None:
    p = tmp_path / "f.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(OptiMindError):
        DataConnector().load(str(p))

"""DataService orchestrates the Data Intelligence pipeline."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from opti_mind.data.connector import DataConnector
from opti_mind.data.feature_mapper import FeatureMapper
from opti_mind.data.instance_builder import GenericInstanceBuilder
from opti_mind.data.models import FieldSemantics, OptimizationInstance
from opti_mind.data.profiler import DataProfiler
from opti_mind.data.quality import DataQualityChecker
from opti_mind.data.schema import ISchemaInterpreter, create_schema_interpreter


class DataService:
    """Data Intelligence Layer facade.

    Pipeline: connector -> profiler -> quality -> schema -> mapper -> instance.
    """

    def __init__(self, schema_interpreter: ISchemaInterpreter | None = None) -> None:
        self.connector = DataConnector()
        self.profiler = DataProfiler()
        self.quality_checker = DataQualityChecker()
        self.schema_interpreter = schema_interpreter or create_schema_interpreter()
        self.feature_mapper = FeatureMapper()
        self.instance_builder = GenericInstanceBuilder()
        self._last_semantics: list[FieldSemantics] | None = None

    def load_df(self, source: str) -> pd.DataFrame:
        """Load a raw DataFrame from the given source identifier."""
        return self.connector.load(source)

    def build_instance_from_file(self, source: str) -> OptimizationInstance:
        df = self.load_df(source)
        dataset_id = Path(source).stem
        return self.build_instance(df, dataset_id=dataset_id)

    def build_instance(
        self,
        df: pd.DataFrame,
        *,
        dataset_id: str | None = None,
        problem_type: str | None = None,
    ) -> OptimizationInstance:
        # Quality check is informational; it records issues but does not block yet.
        _quality = self.quality_checker.check(df)
        profile = self.profiler.profile(df)
        columns = list(df.columns)
        semantics = self.schema_interpreter.interpret(columns, profile)
        return self.rebuild_instance(
            df, semantics, dataset_id=dataset_id, problem_type=problem_type
        )

    def rebuild_instance(
        self,
        df: pd.DataFrame,
        semantics: list[FieldSemantics],
        dataset_id: str | None = None,
        problem_type: str | None = None,
    ) -> OptimizationInstance:
        """Build an OptimizationInstance from an already-determined semantics map."""
        self._last_semantics = semantics
        mapped = self.feature_mapper.map(df, semantics)
        return self.instance_builder.build(
            mapped, df, semantics, dataset_id=dataset_id, problem_type=problem_type
        )

    def get_last_semantics(self) -> list[FieldSemantics] | None:
        """Return semantics from the most recent build_instance call."""
        return self._last_semantics

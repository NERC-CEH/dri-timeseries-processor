"""
An orchestration class used to run derivations.
"""

import logging

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.derivation.derivation_methods import DerivationMethod
from dritimeseriesprocessor.operations.flags.flag_names import core_flag_column_name
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from dritimeseriesprocessor.utils.enums import ConfigurationType
from dritimeseriesprocessor.utils.polars_utils import missing_expr

logger = logging.getLogger(__name__)


class DerivationPipeline(OperationPipeline):
    """Pipeline for running Derivation methods on a TimeSeriesContainer."""

    def __init__(self, site_metadata: SiteMetadata, flag_systems: dict[str, dict[str, int]]):
        super().__init__(ConfigurationType.DERIVATION, flag_systems)
        self._site_metadata = site_metadata

    def run(
        self,
        container: TimeSeriesContainer,
        dataset_repository: dict[str, TimeSeriesContainer],
        config: DataProcessingConfig,
    ) -> ts.TimeFrame:
        """Run derivation, injecting container context into each method config before processing."""
        for cfg in config.method_configs:
            cfg.params["site_metadata"] = self._site_metadata
            cfg.params["container"] = container
            cfg.params["output_col"] = container.source_column
            cfg.params["resolution"] = container.resolution
            cfg.params["periodicity"] = container.periodicity

        return super().run(container, dataset_repository, config)

    def apply(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig, dataset_repository: dict) -> ts.TimeFrame:
        """Apply the given derivation method to the TimeFrame data.

        Args:
            tf: Time series frame to derive, or `None` for generate-from-scratch derivations.
            config: Configuration of the derivation method.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Result of applying the derivation method.
        """
        config.params["dataset_repository"] = dataset_repository

        dep_ids = []
        for key in ("dep_ts", "load_dep_ts"):
            values = config.params.get(key) or []
            if isinstance(values, str):
                dep_ids.append(values)
            else:
                dep_ids.extend(values)

        for dep_id in dep_ids:
            dep_container = dataset_repository[dep_id]
            if dep_container.source_column:
                config.params[dep_container.source_column.lower()] = dep_container.data

        method = DerivationMethod.get(config.method)
        tf = method.run(config)
        return tf

    def get_flag_column(self, column: str) -> str | None:
        """Derivation does not produce its own flag column."""
        return None

    def compute_flag_mask(self, tf: ts.TimeFrame, result: ts.TimeFrame, column_name: str) -> pl.Series:
        """Not used by derivation - flags are not applied."""
        raise NotImplementedError

    def core_flag_updater(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """Stamp the 'missing' core flag on rows that have no derived value.

        Args:
            tf: TimeFrame with flags to update.

        Returns:
            TimeFrame with the 'missing' core flag applied.
        """
        for data_column in tf.data_columns:
            core_flag_col_name = core_flag_column_name(data_column)
            if core_flag_col_name in tf.flag_columns:
                tf.add_flag(core_flag_col_name, "missing", missing_expr(data_column, tf.df[data_column].dtype))
        return tf

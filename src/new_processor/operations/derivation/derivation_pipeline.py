"""
An orchestration class used to run derivations.
"""

import logging
from typing import Any

import time_stream as ts

from new_processor.models.domain_models.processing_config import ProcessingMethodConfig
from new_processor.models.domain_models.time_series_container import TimeSeriesContainer
from new_processor.operations.derivation.derivation_methods import DerivationMethod
from new_processor.operations.flags.flag_methods import add_initial_core_flags

logger = logging.getLogger(__name__)


class DerivationPipeline:
    """Pipeline for running Derivation methods on a TimeSeriesContainer."""

    def run(self, container: TimeSeriesContainer, dataset_repository: dict[str, TimeSeriesContainer]) -> ts.TimeFrame:
        """Execute the derivation workflow on the time series container.

        Args:
            container: Time series container of metadata and data for the primary dataset to process.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            The new derived TimeFrame.
        """
        config = self._create_derivation_method_config(container, dataset_repository)
        method = DerivationMethod.get(config.method)
        tf = method.run(config)

        tf = add_initial_core_flags(tf, init_unchecked=False)

        return tf

    @staticmethod
    def _create_derivation_method_config(
        container: TimeSeriesContainer, dataset_repository: dict[str, TimeSeriesContainer]
    ) -> ProcessingMethodConfig:
        """Create the method config for the derivation.

        Args:
            container: Time series container containing the metadata needed for the derivation method.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Method configuration properties
        """
        params: dict[str, Any] = {
            "output_col": container.source_column,
            "resolution": container.resolution,
            "periodicity": container.periodicity,
        }
        for ds_id in container.direct_depends_on:
            dep_container = dataset_repository[ds_id]
            params[dep_container.source_column.lower()] = dep_container.data

        return ProcessingMethodConfig(method=container.method.name, params=params)

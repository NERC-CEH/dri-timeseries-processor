"""
Domain model representing a time series dataset within the processing pipeline.

This class abstracts away the complex nested structure of the metadata API, providing a simplified representation
for use in the DAG builder and data processing pipeline.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingConfig
from dritimeseriesprocessor.utils.enums import ConfigurationType, DatasetType, MethodType, ProcessingLevel

logger = logging.getLogger(__name__)


@dataclass
class TimeSeriesContainer:
    ts_id: str
    network: str | None

    source_bucket: str | None
    source_dataset: str | None
    source_column: str | None
    source_site: str | None
    source_site_identifier: str | None
    time_column_name: str | None

    resolution: str | None
    periodicity: str | None
    processing_level: ProcessingLevel

    dataset_type: DatasetType | None = None
    distribution_url: str | None = None

    method_config: DataProcessingConfig | None = None
    correction_configs: set[DataProcessingConfig] = field(default_factory=set)
    qc_configs: set[DataProcessingConfig] = field(default_factory=set)
    infill_configs: set[DataProcessingConfig] = field(default_factory=set)

    data: ts.TimeFrame | None = None
    failed: bool = False  # Set to True if anything goes wrong during the processing pipeline for this dataset
    load_only: bool = False

    def _ids_across_configs(self, *keys: str) -> list[str]:
        """Collect and deduplicate values from the given parameter keys across all attached configs.

        Args:
            keys: One or more parameter key names to extract values from (e.g. `dep_ts`, `load_dep_ts`).

        Returns:
            Sorted, deduplicated list of values collected from all attached configs for the given keys.
        """
        method_config = {self.method_config} if self.method_config else set()
        deps = set()
        for c in self.correction_configs | self.qc_configs | self.infill_configs | method_config:
            deps.update(c._values_for_params(*keys))
        return sorted(deps)

    def all_dependencies(self) -> list[str]:
        """Get a list of all dataset IDs that are dependents of this TimeSeriesContainer, including
        from "dep_ts" and "load_dep_ts" dependency references.

        Returns:
            Sorted list of all dependency dataset IDs.
        """
        return self._ids_across_configs("dep_ts", "load_dep_ts")

    def load_only_dependencies(self) -> list[str]:
        """Get a list of dataset IDs that are "load only" dependents of this TimeSeriesContainer. Only includes
        IDs from "load_dep_ts" references across all attached configs.

        Returns:
            Sorted list of dataset IDs that should be loaded but not processed or saved.
        """
        return self._ids_across_configs("load_dep_ts")

    def attach_configs(self, configs: list[DataProcessingConfig]) -> None:
        """Attach data processing configuration objects (QC, infilling, correction) to this container.

        Args:
            configs: A list of the `ProcessingConfig` objects to attach.
        """
        for config in configs:
            if config.config_type == ConfigurationType.QUALITY_CONTROL:
                self.qc_configs.add(config)

            elif config.config_type == ConfigurationType.INFILLING:
                self.infill_configs.add(config)

            elif config.config_type == ConfigurationType.CORRECTION:
                self.correction_configs.add(config)

            elif config.config_type in (
                ConfigurationType.AGGREGATION,
                ConfigurationType.DERIVATION,
                ConfigurationType.PROCESS,
                ConfigurationType.LOAD_LOCAL_COPY,
            ):
                # Should only ever have one of these
                if self.method_config:
                    raise ValueError(f"A method config already exists: {self.method_config}")
                self.method_config = config

            elif config.config_type == ConfigurationType.CALIBRATION_CORRECTION:
                # TODO: Implement calibration correction processing type
                logger.warning("Calibration correction configuration type not yet implemented.")

            else:
                raise TypeError(f"Unknown configuration type: {config.config_type}")

    def method_type(self) -> MethodType:
        if not self.method_config:
            return MethodType.LOAD
        return MethodType(self.method_config.config_type.value)

    @property
    def s3_bucket(self) -> str | None:
        if self.dataset_type == DatasetType.OBSERVATION_DATASET and self.distribution_url:
            return self.distribution_url.split("://")[1].split("/")[0]
        return self.source_bucket

    @property
    def s3_dataset_path(self) -> str | None:
        if self.dataset_type == DatasetType.OBSERVATION_DATASET and self.distribution_url:
            parts = self.distribution_url.split("://")[1].split("/", 1)
            return parts[1].rstrip("/") if len(parts) > 1 else None
        return self.source_dataset

    def init_timeframe(self, df: pl.DataFrame) -> None:
        """Wrap a DataFrame in a TimeFrame, apply initial flags, and store it on the container.

        If the DataFrame is empty, a warning is logged and the container's data is left unset.

        Args:
            df: The raw DataFrame to wrap.
        """
        if df.is_empty():
            return

        tf = (
            ts.TimeFrame(
                df=df,
                time_name=self.time_column_name,
                resolution=self.resolution,
                periodicity=self.periodicity,
            )
            .with_metadata({"column_name": self.source_column})
            .pad()
        )
        self.data = tf

    def __hash__(self) -> int:
        """Allow this container to be used as a dict or set key."""
        return hash(self.ts_id)


def group_containers(
    containers: tuple[TimeSeriesContainer, ...], attributes: list[str]
) -> dict[tuple, list[TimeSeriesContainer]]:
    """Group containers by a composite key derived from the given attributes.

    Args:
        containers: The containers to group.
        attributes: Container attribute names to form the grouping key.

    Returns:
        A dictionary mapping attribute tuples to lists of containers sharing those attribute values.
    """
    groupings: dict[tuple, list[TimeSeriesContainer]] = defaultdict(list)
    for container in containers:
        key = tuple(getattr(container, attr) for attr in attributes)
        groupings[key].append(container)
    return groupings


def check_common_attributes(containers: list[TimeSeriesContainer], attr: str | list[str]) -> Any | list[Any] | None:
    """Check if all the containers have the same value for each of the given attributes.

    Args:
        containers: List of containers to check attributes for.
        attr: Single or multiple attributes to check for.

    Returns:
        The common value(s) of each of the attribute(s).
    """
    if not containers:
        return None

    if isinstance(attr, str):
        attr = [attr]

    values = []
    first = containers[0]
    for a in attr:
        base = getattr(first, a)
        if not all([getattr(item, a) == base for item in containers]):
            raise ValueError(f"Not all containers have the same attribute value: {a}")
        values.append(base)

    if len(values) == 1:
        return values[0]
    else:
        return values

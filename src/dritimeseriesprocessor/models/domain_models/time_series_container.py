"""
Domain model representing a time series dataset within the processing pipeline.

This class abstracts away the complex nested structure of the metadata API, providing a simplified representation
for use in the DAG builder and data processing pipeline.
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingConfig
from dritimeseriesprocessor.utils.enums import ConfigurationType, MethodType, ProcessingLevel

logger = logging.getLogger(__name__)


@dataclass
class TimeSeriesContainer:
    ts_id: str
    network: str

    source_bucket: str | None
    source_dataset: str | None
    source_column: str
    source_site: str
    source_site_identifier: str
    time_column_name: str

    resolution: str
    periodicity: str
    processing_level: ProcessingLevel

    method_config: DataProcessingConfig | None = None
    correction_configs: set[DataProcessingConfig] = field(default_factory=set)
    qc_configs: set[DataProcessingConfig] = field(default_factory=set)
    infill_configs: set[DataProcessingConfig] = field(default_factory=set)

    data: ts.TimeFrame | None = None
    failed: bool = False  # Set to True if anything goes wrong during the processing pipeline for this dataset
    load_only: bool = False

    def _ids_across_configs(self, fn: Callable[[DataProcessingConfig], list[str]]) -> list[str]:
        """Collect and deduplicate dataset IDs from all attached configs using the given accessor.

        Iterates over all correction, QC, infill, and method configs attached to this container,
        calls ``fn`` on each to retrieve a list of IDs, and returns a sorted, deduplicated result.

        Args:
            fn: A callable that accepts a ``DataProcessingConfig`` and returns a list of dataset ID strings.

        Returns:
            Sorted, deduplicated list of dataset IDs collected from all attached configs.
        """
        method_config = {self.method_config} if self.method_config else set()
        deps = set()
        for c in self.correction_configs | self.qc_configs | self.infill_configs | method_config:
            deps.update(fn(c))
        return sorted(deps)

    def all_dependencies(self) -> list[str]:
        """Get a list of all dataset IDs that are dependents of this TimeSeriesContainer, including
        from "dep_ts" and "load_dep_ts" dependency references.

        Returns:
            Sorted list of all dependency dataset IDs.
        """
        return self._ids_across_configs(DataProcessingConfig.all_dep_ts)

    def load_only_dependencies(self) -> list[str]:
        """Get a list of dataset IDs that are "load only" dependents of this TimeSeriesContainer. Only includes
        IDs from "load_dep_ts" references across all attached configs.

        Returns:
            Sorted list of dataset IDs that should be loaded but not processed or saved.
        """
        return self._ids_across_configs(DataProcessingConfig.load_only_dep_ts)

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
                ConfigurationType.EDDYPRO,
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

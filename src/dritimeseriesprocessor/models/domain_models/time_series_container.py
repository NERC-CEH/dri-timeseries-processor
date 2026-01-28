"""
Domain model representing a time series dataset within the processing pipeline.

This class abstracts away the complex nested structure of the metadata API, providing a simplified representation
for use in the DAG builder and data processing pipeline.
"""

import logging
from dataclasses import dataclass, field

from time_stream import TimeFrame

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingConfig
from dritimeseriesprocessor.utils.enums import ConfigurationType, MethodType, ProcessingLevel

logger = logging.getLogger(__name__)


@dataclass
class TimeSeriesContainer:
    ts_id: str
    network: str

    source_bucket: str
    source_dataset: str
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

    data: TimeFrame | None = None

    def all_dependencies(self) -> list[str]:
        """Return a deduplicated list of all dependencies."""
        method_config = {self.method_config} if self.method_config else set()
        deps = set()
        for c in self.correction_configs | self.qc_configs | self.infill_configs | method_config:
            deps.update(c.all_dep_ts())

        return sorted(deps)

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

    def __hash__(self) -> int:
        """Allow this container to be used as a dict or set key."""
        return hash(self.ts_id)

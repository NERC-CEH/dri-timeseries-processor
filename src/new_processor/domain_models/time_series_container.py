"""
Domain model representing a time series dataset within the processing pipeline.

This class abstracts away the complex nested structure of the metadata API, providing a simplified representation
for use in the DAG builder and data processing pipeline.
"""

from dataclasses import dataclass, field

from time_stream import TimeFrame

from new_processor.domain_models.processing_config import ProcessingConfig
from new_processor.utils.enums import ConfigurationType, MethodType, ProcessingLevel


@dataclass
class TimeSeriesContainer:
    ts_id: str
    ref_id: str

    source_bucket: str
    source_dataset: str
    source_column: str
    source_site: str

    resolution: str
    periodicity: str
    processing_level: ProcessingLevel
    variable: str
    method_type: MethodType | None = None
    method: str | None = None

    depends_on: list[str] = field(default_factory=list)
    direct_depends_on: list[str] = field(default_factory=list)

    correction_configs: set[ProcessingConfig] = field(default_factory=set)
    qc_configs: set[ProcessingConfig] = field(default_factory=set)
    infill_configs: set[ProcessingConfig] = field(default_factory=set)

    data: TimeFrame | None = None

    def all_dependencies(self) -> list[str]:
        """Return a deduplicated list of all dependencies, including config-based."""
        deps = set(self.depends_on)
        for c in self.correction_configs | self.qc_configs | self.infill_configs:
            deps.update(c.all_dep_ts())

        return sorted(deps)

    def load(self) -> bool:
        """If the time series doesn't have a method then this is a "base" level time series that we can load from the
        raw bucket
        """
        return self.method is None

    def attach_configs(self, configs: list[ProcessingConfig]) -> None:
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
            else:
                raise TypeError(f"Unknown configuration type: {config.config_type}")

    def __hash__(self) -> int:
        """Allow this container to be used as a dict or set key."""
        return hash(self.ts_id)

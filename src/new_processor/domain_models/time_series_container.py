"""
Domain model representing a time series dataset within the processing pipeline.

This class abstracts away the complex nested structure of the metadata API, providing a simplified representation
for use in the DAG builder and data processing pipeline.
"""

from dataclasses import dataclass, field

from src.new_processor.domain_models.processing_config import ProcessingConfig
from src.new_processor.utils.enums import MethodType, ProcessingLevel
from time_stream import TimeFrame


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

    correction_configs: list[ProcessingConfig] = field(default_factory=list)
    qc_configs: list[ProcessingConfig] = field(default_factory=list)
    infill_configs: list[ProcessingConfig] = field(default_factory=list)

    data: TimeFrame | None = None

    def all_dependencies(self) -> list[str]:
        """Return a deduplicated list of all dependencies, including config-based."""
        deps = set(self.depends_on)
        for c in self.correction_configs + self.qc_configs + self.infill_configs:
            deps.update(c.all_dep_ts())

        return sorted(deps)

    def load(self) -> bool:
        """If the time series doesn't have a method then this is a "base" level time series that we can load from the
        raw bucket
        """
        return self.method is None

    def __hash__(self) -> int:
        """Allow this container to be used as a dict or set key."""
        return hash(self.ts_id)

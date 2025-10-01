from dataclasses import dataclass, field
from typing import List

from time_stream import TimeSeries

from metadata_manager.models.schemas.data_processing_configurations import (
    DataProcessingConfiguration,
)


@dataclass
class TimeseriesContainer:
    """A container for timeseries metadata.

    Attributes:
        ts_def: The timeseries definition.
        resolution: The resolution of the timeseries.
        periodicity: The periodicity of the timeseries.
        processing_level: The processing level of the timeseries.
        sourceBucket: The source S3 bucket.
        sourceDataset: The source dataset.
        sourceColumnName: The source column name.
        sourceSite: The source site.
        data: The timeseries data.
    """

    ts_def: str
    resolution: str
    periodicity: str
    processing_level: str
    sourceBucket: str
    sourceDataset: str
    sourceColumnName: str
    sourceSite: str
    method_type: str | None = None
    method: str | None = None
    inputs: List[str] = field(default_factory=list)
    load: bool = False
    data: TimeSeries | None = None
    correction_configs: List[DataProcessingConfiguration] = field(default_factory=list)
    qc_configs: List[DataProcessingConfiguration] = field(default_factory=list)
    infill_configs: List[DataProcessingConfiguration] = field(default_factory=list)

    @property
    def load_data(self) -> bool:
        if self.processing_level == "raw" and not self.method:
            return True
        return False

from dataclasses import dataclass, field
from typing import List

from time_stream import TimeFrame

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
        method_type: The type of method to apply  if relevant (e.g aggregation or derivation ).
        method: The method to apply (e.g. for aggregation or derivation)
        inputs: A list of ts_ids which are required to calculate the final data product
        load: Whether or not to load any raw data
        data: The time series data.
        correction_configs: A list of DataProcessingConfiguration options, each corresponding to a correction that needs
            applying
        qc_configs: A list of DataProcessingConfiguration options, each corresponding to a quality control method that
            needsapplying
        infill_configs: A list of DataProcessingConfiguration options, each corresponding to a infilling method that
            needs applying
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
    data: TimeFrame | None = None
    correction_configs: List[DataProcessingConfiguration] = field(default_factory=list)
    qc_configs: List[DataProcessingConfiguration] = field(default_factory=list)
    infill_configs: List[DataProcessingConfiguration] = field(default_factory=list)

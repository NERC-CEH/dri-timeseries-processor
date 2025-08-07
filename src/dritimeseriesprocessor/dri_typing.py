"""Types for processing."""

from typing import List, NotRequired, TypedDict

from time_stream import TimeSeries


class TimeseriesContainer(TypedDict):
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
    data: NotRequired[TimeSeries]


class DerivationMetadata(TypedDict):
    """Derivation metadata.

    Attributes:
        method_type: The type of derivation method.
        method: The derivation method.
        inputs: A list of input timeseries IDs.
        load: Whether to load the data for this timeseries.
    """

    method_type: str | None
    method: str | None
    inputs: List[str]
    load: NotRequired[bool]


class TimeseriesContainerWithDerivations(TimeseriesContainer, DerivationMetadata):
    """Timeseries Container with derivation info.

    Inherits all attributes from TimeseriesContainer and DerivationMetadata.
    """

    pass

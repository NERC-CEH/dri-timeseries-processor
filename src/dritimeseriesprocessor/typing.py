"""Types for processing."""

from typing import List, TypedDict


class TimeseriesMetadata(TypedDict):
    """Timeseries Metadata.

    Attributes:
        ts_def: The timeseries definition.
        resolution: The resolution of the timeseries.
        periodicity: The periodicity of the timeseries.
        processing_level: The processing level of the timeseries.
        sourceBucket: The source S3 bucket.
        sourceDataset: The source dataset.
        sourceColumnName: The source column name.
        sourceSite: The source site.
    """

    ts_def: str
    resolution: str
    periodicity: str
    processing_level: str
    sourceBucket: str
    sourceDataset: str
    sourceColumnName: str
    sourceSite: str


class DerivationMetadata(TypedDict):
    """Derivation metadata.

    Attributes:
        method_type: The type of derivation method.
        method: The derivation method.
        inputs: A list of input timeseries IDs.
    """

    method_type: str | None
    method: str | None
    inputs: List[str]


class TimeseriesMetadataWithDerivations(TimeseriesMetadata):
    """Timeseries metadata with derivation info.

    Attributes:
        method_type: The type of derivation method.
        method: The derivation method.
        inputs: A list of input timeseries IDs.
        load: Whether to load the data for this timeseries.
    """

    method_type: str | None
    method: str | None
    inputs: List[str]
    load: bool

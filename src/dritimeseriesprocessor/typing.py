"""Custom types for the application."""

from typing import TypedDict


class TimeseriesMetadata(TypedDict):
    """A type definition for timeseries metadata."""

    ts_def: str
    resolution: str
    periodicity: str
    processing_level: str
    sourceBucket: str
    sourceDataset: str
    sourceColumnName: str
    sourceSite: str

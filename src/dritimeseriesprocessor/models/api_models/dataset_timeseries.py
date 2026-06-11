"""
Pydantic models for the Time Series Dataset, with timeseries view, metadata endpoint.

Example API call:
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/{dataset_id}.json?_view=timeseries

Represents metadata describing time series datasets, including their measurement details (variable, unit, resolution),
processing level, data location, etc. Used to parse and validate dataset metadata before mapping to
domain models and building dependency graphs.
"""

from pydantic import Field

from dritimeseriesprocessor.models.api_models.dataset_observation import ObservationDatasetItem
from dritimeseriesprocessor.models.api_models.flags import FlagColumn
from dritimeseriesprocessor.models.api_models.shared import BaseAPIResponse


class TimeSeriesDatasetItem(ObservationDatasetItem):
    """Time series dataset item - extends ObservationDatasetItem"""

    source_bucket: str | None = Field(None, alias="sourceBucket")
    source_dataset: str | None = Field(None, alias="sourceDataset")
    source_column_name: str | None = Field(None, alias="sourceColumnName")
    time_column_name: str | None = Field(None, alias="sourceTimeColumnName")
    has_flag_column: list[FlagColumn] | None = Field(default_factory=list, alias="hasFlagColumn")


class TimeSeriesDatasetResponse(BaseAPIResponse):
    """Time series dataset API response."""

    items: list[TimeSeriesDatasetItem]

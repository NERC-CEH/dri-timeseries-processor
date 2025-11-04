"""
Pydantic models for the Dataset Dependencies metadata endpoint.

Example API call:
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/{dataset_id}/_dependencies.json
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/{dataset_id}/_all_dependencies.json

Represents the instance-ready dependencies of a time series dataset, as returned by the FDRI metadata API.
"""

from new_processor.api_models.dataset_timeseries import TimeSeriesDatasetItem
from new_processor.api_models.shared import BaseAPIResponse


class DatasetDependencies(BaseAPIResponse):
    """Dataset dependencies API response."""

    items: list[TimeSeriesDatasetItem]

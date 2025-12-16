"""
Metadata Router

Provides a routing layer for metadata API requests, delegating calls to the APi manager.
Constructs the appropriate API endpoints for datasets and data-processing configurations, handling parameterised
queries and dependency lookups.
"""

from new_processor.externals.api_manager import MetadataAPIManager
from new_processor.models.api_models.data_processing_configuration import DataProcessingConfiguration
from new_processor.models.api_models.dataset_timeseries import TimeSeriesDatasetResponse
from new_processor.models.api_models.network import Network
from new_processor.models.api_models.site import SiteResponse
from new_processor.utils.batching import batched
from new_processor.utils.enums import ConfigurationType
from new_processor.utils.urls import CONFIGURATION_TYPE_URI


class MetadataRouter:
    """Route metadata API requests to the correct URL via the API manager."""

    def __init__(self, host: str):
        """Initialise the metadata router.

        Args:
            host: Base URL of the metadata API.
        """
        self.host = host
        self.api_manager = MetadataAPIManager(host=self.host)

    def fetch_dataset_by_params(self, query_params: tuple[tuple[str, str], ...]) -> TimeSeriesDatasetResponse:
        """Fetch dataset metadata using query parameters.

        Args:
            query_params: Tuple of key–value pairs representing query parameters.

        Returns:
            The parsed JSON response containing datasets matching the provided parameters.
        """
        url = f"{self.host}/id/dataset"
        response = self.api_manager.make_paginated_api_call(url, query_params)
        return TimeSeriesDatasetResponse.model_validate(response)

    def fetch_dataset_by_id(self, dataset_id: str) -> TimeSeriesDatasetResponse:
        """Fetch a dataset by its ID, using the `_view=timeseries` endpoint

        Args:
            dataset_id: The dataset ID.

        Returns:
            The parsed JSON response for the specified dataset.
        """
        url = f"{self.host}/id/dataset/{dataset_id}?_view=timeseries"
        response = self.api_manager.make_paginated_api_call(url)
        return TimeSeriesDatasetResponse.model_validate(response)

    def fetch_all_dependencies(self, dataset_id: str) -> TimeSeriesDatasetResponse:
        """Fetch all dependencies for a dataset. This uses the `_all_dependencies` endpoint which provides nested
        (recursive) dependencies for a given dataset.

        Args:
            dataset_id: The dataset identifier for which dependencies should be retrieved.

        Returns:
            The parsed JSON response containing all dataset dependencies, including nested ones.
        """
        url = f"{self.host}/id/dataset/{dataset_id}/_all_dependencies"
        response = self.api_manager.make_paginated_api_call(url)
        return TimeSeriesDatasetResponse.model_validate(response)

    def fetch_processing_configs(self, dataset_ids: list[str], batch_size: int = 50) -> DataProcessingConfiguration:
        """Fetch data processing configuration metadata (e.g. for QC, Infill, Corrections)

        Args:
            dataset_ids: The dataset identifier(s) for which processing configs should be retrieved.
            batch_size: Number of datasets to fetch processing configs for at a time. Required in case user has
                        requested large number of datasets (e.g. all sites, all variables) which builds a URL that
                        is too long (HTTP 414).

        Returns:
            The parsed JSON response containing data processing configurations.
        """
        config_type_params = [("type", f"{CONFIGURATION_TYPE_URI}/{ct.value}") for ct in ConfigurationType]

        # Do this in batches in case we have a huge number of datasets to get through (built URL can be huge!)
        merged_response = {"meta": {}, "items": []}
        for batch in batched(dataset_ids, batch_size):
            dataset_params = [("appliesToTimeSeries", dataset_id) for dataset_id in batch]
            query_params = tuple(config_type_params + dataset_params)
            url = f"{self.host}/id/data-processing-configuration"
            response = self.api_manager.make_paginated_api_call(url, query_params)

            merged_response["meta"] = response["meta"]
            merged_response["items"].extend(response["items"])

        return DataProcessingConfiguration.model_validate(merged_response)

    def fetch_sites(self, site_ids: list[str]) -> SiteResponse:
        """Fetch site metadata for given site ID(s).

        Args:
            site_ids: ID(s) of the site(s) to fetch.

        Returns:
            The parsed JSON response containing site metadata.
        """
        url = f"{self.host}/id/site?_view=annotated"
        params = tuple(("@id", site_id) for site_id in site_ids)
        response = self.api_manager.make_paginated_api_call(url, params)
        return SiteResponse.model_validate(response)

    def fetch_network(self, network: str) -> Network:
        """Fetch network metadata for given network name

        Args:
            network: Network to fetch metadata for.

        Returns:
            The parsed JSON response containing network metadata.
        """
        url = f"{self.host}/id/network/{network}"
        response = self.api_manager.make_paginated_api_call(url)
        return Network.model_validate(response)

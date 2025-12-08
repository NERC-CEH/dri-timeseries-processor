"""
Metadata Router

Provides a routing layer for metadata API requests, delegating calls to the APi manager.
Constructs the appropriate API endpoints for datasets and data-processing configurations, handling parameterised
queries and dependency lookups.
"""

from new_processor.models.api_models.data_processing_configuration import DataProcessingConfiguration
from new_processor.models.api_models.dataset_timeseries import TimeSeriesDatasetResponse
from new_processor.models.api_models.site import SiteResponse
from new_processor.externals.api_manager import MetadataAPIManager
from new_processor.utils.strings import extract_uri_id


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

    def fetch_processing_configs(self, query_params: tuple[tuple[str, str], ...]) -> DataProcessingConfiguration:
        """Fetch data processing configuration metadata (e.g. for QC, Infill, Corrections)

        Args:
            query_params: Tuple of key–value pairs used to filter configuration results.

        Returns:
            The parsed JSON response containing data processing configurations.
        """
        url = f"{self.host}/id/data-processing-configuration"
        response = self.api_manager.make_paginated_api_call(url, query_params)
        return DataProcessingConfiguration.model_validate(response)

    def fetch_site(self, site_id: str) -> SiteResponse:
        """Fetch site metadata for given site ID.

        Args:
            site_id: ID of the site to fetch.

        Returns:
            The parsed JSON response containing site metadata.
        """
        url = f"{self.host}/id/site/{site_id}"
        response = self.api_manager.make_paginated_api_call(url)
        return SiteResponse.model_validate(response)

    def fetch_site_by_alt_id(self, alt_site_id: str) -> SiteResponse:
        """Fetch site metadata for given alt site ID - the "identifier" field in the API metadata

        e.g. BUNNY instead of cosmos-bunny for the COSMOS network.

        # TODO: This is a bit of a workaround until we have a better mechanism for fetching site metadata, e.g. see
            https://github.com/NERC-CEH/fdri-discovery/issues/248

        Args:
            alt_site_id: Alternative ID of the site to fetch.

        Returns:
            The parsed JSON response containing site metadata.
        """
        url = f"{self.host}/id/site"
        params = (("identifier", alt_site_id),)
        response = self.api_manager.make_paginated_api_call(url, params)
        site_id = extract_uri_id(response["items"][0]["@id"])
        return self.fetch_site(site_id)

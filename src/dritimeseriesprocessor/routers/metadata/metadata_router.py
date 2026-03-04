"""
Metadata Router

Provides a routing layer for metadata API requests, delegating calls to the APi manager.
Constructs the appropriate API endpoints for datasets and data-processing configurations, handling parameterised
queries and dependency lookups.
"""

from itertools import batched
from typing import TypeVar

from driutils.metadata_api.api_manager import MetadataAPIManager
from pydantic import BaseModel

from dritimeseriesprocessor.models.api_models.data_processing_configuration import DataProcessingConfiguration
from dritimeseriesprocessor.models.api_models.dataset_timeseries import TimeSeriesDatasetResponse
from dritimeseriesprocessor.models.api_models.deployment import Deployment
from dritimeseriesprocessor.models.api_models.network import Network
from dritimeseriesprocessor.models.api_models.site import SiteResponse

PydanticModel = TypeVar("PydanticModel", bound=BaseModel)


class MetadataRouter:
    """Route metadata API requests to the correct URL via the API manager."""

    def __init__(self, host: str, api_manager: MetadataAPIManager | None = None):
        """Initialise the metadata router.

        Args:
            host: Base URL of the metadata API.
            api_manager: Optional instance of a MetadataAPIManager object. If none, a default one will be created.
        """
        self.host = host
        self.api_manager = api_manager or MetadataAPIManager(host=self.host)

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

    def fetch_dataset_by_ids(self, dataset_ids: list[str], batch_size: int = 50) -> TimeSeriesDatasetResponse:
        """Fetch datasets from multiple ID, using the `_view=timeseries` endpoint

        Args:
            dataset_ids: The dataset IDs.
            batch_size: Number of datasets to fetch datasetss for at a time. Required in case user has
                        requested large number of datasets (e.g. all sites, all variables) which builds a URL that
                        is too long (HTTP 414).
        Returns:
            The parsed JSON response for the specified datasets.
        """
        url = f"{self.host}/id/dataset"
        fixed_params = [("_view", "timeseries")]
        return self._fetch_by_batch(
            url, "id", dataset_ids, TimeSeriesDatasetResponse, batch_size=batch_size, fixed_params=fixed_params
        )

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
        url = f"{self.host}/id/data-processing-configuration"
        return self._fetch_by_batch(
            url, "appliesToDataset", dataset_ids, DataProcessingConfiguration, batch_size=batch_size
        )

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

    def fetch_deployment_by_platform(self, platform: str) -> Deployment:
        """Fetch deployment metadata for the given platform ID

        Args:
            platform: Platform to fetch deployment metadata for.

        Returns:
            The parsed JSON response containing deployment metadata.
        """
        url = f"{self.host}/id/deployment"
        params = (("deployedOnPlatform", platform),)
        response = self.api_manager.make_paginated_api_call(url, params)
        return Deployment.model_validate(response)

    def _fetch_by_batch(
        self,
        url: str,
        param: str,
        values: list[str],
        model: type[PydanticModel],
        fixed_params: list[tuple[str, str]] | None = None,
        batch_size: int = 50,
    ) -> PydanticModel:
        """Fetch from an endpoint in batches by repeating a query param for each value.

        This helper exists to avoid HTTP 414 (URI Too Long) when requesting many IDs.

        Args:
            url: Endpoint url.
            param: The query parameter key used for each value (e.g. "id", "appliesToTimeSeries").
            values: List of values to repeat for given param.
            model: Pydantic model class used to validate the merged response.
            fixed_params: Additional query params added to every request (e.g. ("_view", "timeseries")).
            batch_size: Number of values to use per request.

        Returns:
            A validated model built from the merged batched responses.
        """

        merged_response = {"meta": {}, "items": []}

        if not fixed_params:
            fixed_params = []

        for batch in batched(values, batch_size):
            dataset_params = [(param, batch_value) for batch_value in batch]
            response = self.api_manager.make_paginated_api_call(url, tuple(dataset_params + fixed_params))
            merged_response["meta"] = response["meta"]
            merged_response["items"].extend(response["items"])

        return model.model_validate(merged_response)

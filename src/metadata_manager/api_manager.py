"""Module to handle calls to the metadata API."""

import logging
from typing import Any, Dict

from httpx import AsyncClient, HTTPError

logger = logging.getLogger(__name__)


class MetadataAPIManager:
    """Manage requests to the metadata API."""

    def __init__(self, host: str, network: str) -> None:
        """Initialise the API Manager

        Args:
            host: host URL for the metadata API
            network: what network of sensors to query
        """
        self.host = host
        self.network = network
        self.service_base_uri = "http://fdri.ceh.ac.uk"

    async def _make_api_call(self, url: str, params: Dict[str, str] = None) -> Dict[str, Any]:
        """Make a call to the metadata API.

        Args:
            url: The request url.
            params: The request params. Defaults to None.

        Returns:
            The JSON response from the API

        Raises:
            HTTP exception if the API request fails or returns an error.
        """
        async with AsyncClient() as client:
            try:
                response = await client.get(url=url, params=params)
                response.raise_for_status()
                logger.debug(f"Trying to access: {response.url}")
                return response.json()
            except HTTPError as e:
                logger.error(f"Failed to fetch {self.network} data: {str(e)}")
                logger.exception(e)
                raise e

    async def fetch_sites(self) -> Dict[str, Any]:
        """Fetch all sites from the specified network.

        Returns:
            JSON response containing site information for the network.

        Raises:
            HTTPError: If the API request fails.
        """
        response = await self._make_api_call(f"{self.host}/id/network/{self.network}")
        return response

    async def fetch_infill_configs(self, site_id: str = None) -> Dict[str, Any]:
        """Fetch infill configurations, optionally filtered by site ID.

        Args:
            site_id: Site identifier to filter configurations. Defaults to None, returns all infill configurations.
        
        Returns:
            JSON response containing infill configurations.

        Raises:
            HTTPError: If the API request fails.
        """
        url = (
            f"{self.host}/id/data-processing-configuration.json?"
            f"type={self.service_base_uri}/ref/common/configuration-type/infill-configuration"
        )

        if site_id:
            url += f"&appliesToFacility={self.service_base_uri}/id/site/{self.network}-{site_id.lower()}"

        response = await self._make_api_call(url)

        return response

    async def fetch_timeseries_metadata(self, timeseries_id: str = None) -> Dict[str, Any]:
        """Fetch metadata for a specific time series.
        
        Args:
            timeseries_id: Identifier for the time series to fetch metadata for.
        
        Returns:
            JSON response containing time series metadata.
        
        Raises:
            HTTPError: If the API request fails.
        """
        url = f"{self.host}/id/dataset.json?@id={self.service_base_uri}/id/dataset/{timeseries_id}&_view=timeseries"
        response = await self._make_api_call(url)
        return response

    async def fetch_dataset_metadata(self, parameters: Dict) -> Dict[str, Any]:
        """Fetch metadata for a specific dataset
        
        Args:
            parameters: API query parameters for the dataset endpoint
        
        Returns:
            JSON response containing time series ID metadata.
        
        Raises:
            HTTPError: If the API request fails.
        """
        url = f"{self.host}/id/dataset"
        response = await self._make_api_call(url, parameters)

        # TODO: Functionality to handle pagination if more than 25 records returned FW-692

        return response

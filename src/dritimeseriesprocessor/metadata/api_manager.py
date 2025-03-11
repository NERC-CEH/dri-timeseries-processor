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
        response = await self._make_api_call(f"{self.host}/id/network/{self.network}")
        return response

    async def fetch_infill_configs(self, site_id: str = None) -> Dict[str, Any]:
        url = (
            f"{self.host}/id/data-processing-configuration.json?"
            f"type={self.service_base_uri}/ref/common/configuration-type/infill-configuration"
        )

        if site_id:
            url += f"&appliesToFacility={self.service_base_uri}/id/site/{self.network}-{site_id.lower()}"

        response = await self._make_api_call(url)

        return response

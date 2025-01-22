"""Module to handle calls to the metadata API."""

import logging
from typing import Any, Dict

from httpx import AsyncClient, HTTPError

logger = logging.getLogger(__name__)


class MetadataAPIManager:
    """Manage requests to the metadata API."""

    def __init__(self, network: str) -> None:
        """Initialise the API Manager

        Args:
            network: what network of sensors to query
        """
        self.host = "https://dri-metadata-api.staging.eds.ceh.ac.uk"
        self.network = network

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
        logger.info(f"Connecting to {self.host}")

        async with AsyncClient() as client:
            try:
                response = await client.get(url=url, params=params)
                logger.info(f"Trying to access: {response.url}")
                return response.json()
            except HTTPError as e:
                logger.error(f"Failed to fetch {self.network} data: {str(e)}")
                logger.exception(e)
                raise e

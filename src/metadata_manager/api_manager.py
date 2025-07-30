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

    async def fetch_infill_config(self, ts_id: str) -> Dict[str, Any]:
        """Fetch infill configurations for a given time series ID.

        Args:
            ts_id: The time series ID to load infill configurations for.
        Returns:
            JSON response containing infill configurations.

        Raises:
            HTTPError: If the API request fails.
        """
        url = (
            f"{self.host}/id/data-processing-configuration.json?"
            f"type={self.service_base_uri}/ref/common/configuration-type/infill-configuration"
            f"&appliesToTimeSeries={ts_id}"
        )

        response = await self._make_api_call(url)

        return response

    async def fetch_qc_config(self, ts_id: str) -> Dict[str, Any]:
        """Fetch QC configurations for a given time series ID.

        Args:
            ts_id: The time series ID to load qc configurations for.
        Returns:
            JSON response containing qc configurations.

        Raises:
            HTTPError: If the API request fails.
        """
        url = (
            f"{self.host}/id/data-processing-configuration.json?"
            f"type={self.service_base_uri}/ref/common/configuration-type/qc"
            f"&appliesToTimeSeries={ts_id}"
        )

        response = await self._make_api_call(url)

        return response

    async def fetch_correction_config(self, ts_id: str) -> Dict[str, Any]:
        """Fetch correction configurations for a given time series ID.

        Args:
            ts_id: The time series ID to load correction configurations for.

        Returns:
            JSON response containing correction configurations.

        Raises:
            HTTPError: If the API request fails.
        """
        url = (
            f"{self.host}/id/data-processing-configuration.json?"
            f"type={self.service_base_uri}/ref/common/configuration-type/correction"
            f"&appliesToTimeSeries={ts_id}"
        )

        response = await self._make_api_call(url)

        return response

    async def fetch_timeseries_metadata(self, parameters: Dict) -> Dict[str, Any]:
        """Fetch metadata for timeseries id(s)

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

    async def fetch_dependent_dataset_metadata(self, timeseries_id: str) -> Dict[str, Any]:
        """Fetch the metadata of any dependencies for a specific dataset

        Args:
            timeseries_id: The ID of the timeseries dataset to fetch dependencies for

        Returns:
            JSON response containing time series ID metadata.

        Raises:
            HTTPError: If the API request fails.
        """
        url = f"{self.host}/id/dataset/{timeseries_id}/_dependencies"
        response = await self._make_api_call(url)

        return response

    async def fetch_timeseries_derivation_metadata(self, timeseries_def: str) -> Dict[str, Any]:
        """Fetch metadata for derivations associated to a timeseries definition

        Args:
            timeseries_def: The timeseries definition ID to fetch derivation metadata for.

        Returns:
            JSON response containing time series derivation metadata.

        Raises:
            HTTPError: If the API request fails.
        """
        base_parameters = {"_view": "derivation"}
        timeseries_def_parameter = {"@id": timeseries_def}
        url = f"{self.host}/ref/time-series-definition"
        response = await self._make_api_call(url, base_parameters | timeseries_def_parameter)

        # TODO: Functionality to handle pagination if more than 25 records returned FW-692

        return response

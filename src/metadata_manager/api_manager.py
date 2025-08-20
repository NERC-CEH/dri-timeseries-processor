"""Module to handle calls to the metadata API."""

import logging
from typing import Any, Dict, List, Tuple

from httpx import AsyncClient, HTTPError

logger = logging.getLogger(__name__)

PAGE_SIZE = 25


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

    async def _make_paginated_api_call(
        self, url: str, params: Dict[str, str] = None, page_size: int = PAGE_SIZE
    ) -> Dict[str, Any]:
        """
        Make a paginated call to the metadata API.

        Due to some metadata API calls not supporting pagination, an initial API call is made first. The response from
        this then provides the information required to determine if further paginated API calls are required.
        If the response indicates no pagination support by the absence of a 'limit' field in the response 'meta' data
        then the initial response is returned directly.
        Similarly, if the response indicates that pagination is supported but fewer items are present in the response
        than the provided limit (e.g. the limit is 25 but the response only contains 3 items), then the initial response
        will be returned directly.

        Args:
            url: URL to request data from
            params: Any supporting parameters to accompany the URL in the request. Defaults to None.
            page_size: The number of items to request at once when making a paginated API call. Defaults to PAGE_SIZE.

        Returns:
            The JSON response from the API. This will be the combined response if pagination is required.

        """
        # Make the initial API response to determine if further paginated API calls are required.
        initial_response = await self._make_api_call(url=url, params=params)
        if "limit" not in initial_response["meta"].keys():
            return initial_response

        if len(initial_response["items"]) < initial_response["meta"]["limit"]:
            return initial_response

        # Ensure params exists. Note that this isn't located at the top of the function as some API calls change their
        # behaviour if any params are provided, even if it's an empty dictionary
        if params is None:
            params = {}

        # Set the offset to a ridiculously high number just to have something to loop over, theoretically this maximum
        # offset should never be reached.
        maximum_offset = 100000000000

        # The initial response meta value can be used for the final response. The core contents (excluding limit and
        # offset) should be the same across all pages.
        response_meta = initial_response["meta"]
        response_items = initial_response["items"]

        params = self._update_params(params, param_key="_limit", param_value=page_size)

        for offset in range(len(response_items), maximum_offset, page_size):
            params = self._update_params(params, param_key="_offset", param_value=offset)

            response_data = await self._make_api_call(url=url, params=params)

            current_items = response_data["items"]
            response_items.extend(current_items)

            # Break the loop once the response data doesn't contain as many items as the page size, as this indicates
            # all values have been fetched.
            if len(current_items) < page_size:
                return {"meta": response_meta, "items": response_items}

    @staticmethod
    def _update_params(params: Dict | List[Tuple], param_key: str, param_value: str) -> Dict | List[Tuple]:
        if isinstance(params, dict):
            params[param_key] = param_value
        elif isinstance(params, list):
            params = [(key, value) for (key, value) in params if key != param_key]
            params.append((param_key, param_value))

        return params

    async def fetch_sites(self) -> Dict[str, Any]:
        """Fetch all sites from the specified network.

        Returns:
            JSON response containing site information for the network.

        Raises:
            HTTPError: If the API request fails.
        """
        response = await self._make_paginated_api_call(f"{self.host}/id/network/{self.network}")
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

        response = await self._make_paginated_api_call(url)

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

        response = await self._make_paginated_api_call(url)

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
            f"type={self.service_base_uri}/ref/common/configuration-type/correction-configuration"
            f"&appliesToTimeSeries={ts_id}"
        )

        response = await self._make_paginated_api_call(url)

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
        response = await self._make_paginated_api_call(url, parameters)

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
        response = await self._make_paginated_api_call(url)

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
        response = await self._make_paginated_api_call(url, base_parameters | timeseries_def_parameter)

        # TODO: Functionality to handle pagination if more than 25 records returned FW-692

        return response

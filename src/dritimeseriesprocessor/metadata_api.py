"""Module to handle calls to the metadata API."""

import json
import logging
from pathlib import Path
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

        Raies:
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

    async def _fetch_variable_metadata(self, site: str, resolution: str) -> Dict[str, Any]:
        """Fetch variable metadata.

        Return the variable name and units for a site and a resolution.

        Args:
            site: The site to query
            resolution: The resolution to query

        Returns:
            Something...
        """

        base_url = f"{self.host}/id/dataset"

        variable_metadata = {}

        # Note: @type doesnt exist in our architecture yet so request fails
        # Loading in static JSON to replicate the response

        # params = {
        #    "@type": "http://fdri.ceh.ac.uk/vocab/metadata/TimeSeriesDataset",
        #    "originatingFacility": f"http://fdri.ceh.ac.uk/id/site/cosmos-{site.lower()}",
        #    "processingLevel": f"http://fdri.ceh.ac.uk/ref/common/processing-level/1",
        #    "temporalResolution": f"{resolution}"
        # }

        f = open(Path(Path(__file__).parents[0], "__metadata__/", "sample_metadata_api.json"))
        response = json.load(f)

        # This returns a list of timeseries' (each one a variable). We currently need to look into
        # each item to get the variable name and unit
        # In discussion with epimorphics about having the metadata at the timeseries level which
        # would mean we dont need to make the second API call
        for dataset in response["items"]:
            timeseries = dataset["@id"].split("/")[-1]
            response = await self._make_api_call(url=f"{base_url}/{timeseries}")

            # Wrap into a function TODO
            for item in response["items"]:
                for prop in item["observedProperty"]:
                    variable_name = prop["@id"].split("/")[-1]

                    if "unitless" not in prop["hasUnit"]["@id"]:
                        variable_unit = prop["unitName"]
                    else:
                        variable_unit = None

                    variable_metadata[variable_name] = variable_unit

        # Need to map between columns in s3 and columns in API
        # If column not in API then delete from loaded data as metadata
        # API is the source of truth.

        # Just returning for the time being.
        return variable_metadata

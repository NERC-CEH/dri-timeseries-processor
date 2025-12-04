"""
Metadata Router

Provides a routing layer for metadata API requests, delegating calls to the APi manager.
Constructs the appropriate API endpoints for datasets and data-processing configurations, handling parameterised
queries and dependency lookups.
"""

import json
from typing import Any

from new_processor import PACKAGE_ROOT
from new_processor.externals.api_manager import MetadataAPIManager


class MetadataRouter:
    """Route metadata API requests to the correct URL via the API manager."""

    def __init__(self, host: str):
        """Initialise the metadata router.

        Args:
            host: Base URL of the metadata API.
        """
        self.host = host
        self.api_manager = MetadataAPIManager(host=self.host)

    def fetch_dataset_by_params(self, query_params: tuple[tuple[str, str], ...]) -> dict[str, Any]:
        """Fetch dataset metadata using query parameters.

        Args:
            query_params: Tuple of key–value pairs representing query parameters.

        Returns:
            The JSON response containing datasets matching the provided parameters.
        """
        url = f"{self.host}/id/dataset"
        return self.api_manager.make_paginated_api_call(url, query_params)

    def fetch_dataset_by_id(self, dataset_id: str) -> dict[str, Any]:
        """Fetch a dataset by its ID, using the `_view=timeseries` endpoint

        Args:
            dataset_id: The dataset ID.

        Returns:
            The JSON response for the specified dataset.
        """
        url = f"{self.host}/id/dataset/{dataset_id}?_view=timeseries"
        return self.api_manager.make_paginated_api_call(url)

    def fetch_all_dependencies(self, dataset_id: str) -> dict[str, Any]:
        """Fetch all dependencies for a dataset. This uses the `_all_dependencies` endpoint which provides nested
        (recursive) dependencies for a given dataset.

        Args:
            dataset_id: The dataset identifier for which dependencies should be retrieved.

        Returns:
            The JSON response containing all dataset dependencies, including nested ones.
        """
        url = f"{self.host}/id/dataset/{dataset_id}/_all_dependencies"
        return self.api_manager.make_paginated_api_call(url)

    def fetch_processing_configs(self, query_params: tuple[tuple[str, str], ...]) -> dict[str, Any]:
        """Fetch data processing configuration metadata (e.g. for QC, Infill, Corrections)

        Args:
            query_params: Tuple of key–value pairs used to filter configuration results.

        Returns:
            The JSON response containing data processing configurations.
        """
        url = f"{self.host}/id/data-processing-configuration"
        return self.api_manager.make_paginated_api_call(url, query_params)


def fetch_core_flags() -> dict[str, Any]:
    """Fetch core flag metadata.  This is a placeholder while a proper metadata store is being built.

    In the future this could call:
        - an internal metadata API
        - an S3 object
        - a PostgreSQL metadata store

    For now, it loads from local JSON.
    """
    path = PACKAGE_ROOT / "__metadata__" / "core_flags.json"
    return json.loads(path.read_text())

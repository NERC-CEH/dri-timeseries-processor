"""
Repositories for dataset and configuration metadata needed for dependency graph resolution.

This module provides repository classes that encapsulate:
    - API access to metadata and configuration endpoints
    - response parsing and domain model mapping
    - caching of fetched datasets to avoid redundant network calls
    - dependency resolution helpers used by the DAG builder
"""

from collections import defaultdict
from typing import Any

from new_processor.api_models.data_processing_configuration import DataProcessingConfiguration
from new_processor.api_models.dataset_timeseries import TimeSeriesDatasetResponse
from new_processor.domain_models.processing_config import ProcessingConfig
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.externals.routers import MetadataRouter
from new_processor.mappers.api_to_domain import map_dataset_item, map_processing_config_item
from new_processor.utils.enums import ConfigurationType, ProcessingLevel
from new_processor.utils.strings import extract_uri_id
from new_processor.utils.urls import CONFIGURATION_TYPE_URI, PROCESSING_LEVEL_URI, SITE_URI


class ConfigRepository:
    def __init__(self, api_router: MetadataRouter):
        self.api_router = api_router

    def fetch_configs_for_dataset(self, dataset_id: str | list[str]) -> dict[str, list[ProcessingConfig]]:
        """Fetch data processing configurations (QC, infilling, correction) that apply to the specified dataset(s).

        Args:
            dataset_id: Single dataset ID or list of dataset IDs.

        Returns:
            Dictionary mapping dataset IDs to their list of processing configurations.
        """
        if not dataset_id:
            return {}

        if isinstance(dataset_id, str):
            dataset_id = [dataset_id]

        config_type_params = [("type", f"{CONFIGURATION_TYPE_URI}/{ct.value}") for ct in ConfigurationType]
        other_params = [("appliesToTimeSeries", d) for d in dataset_id]
        response = self.api_router.fetch_processing_configs(tuple(config_type_params + other_params))

        dataset_configs = self._build_processing_configs(response)
        return dataset_configs

    def _build_processing_configs(self, dataset_response: dict[str, Any]) -> dict[str, list[ProcessingConfig]]:
        """Parse an API response containing processing configuration items and return them grouped by timeseries ID.

        Args:
            dataset_response: The JSON dictionary from the metadata API representing a set of processing configs.

        Returns:
            A dictionary keyed by timeseries ID, with value as the list of associated processing configs.
        """
        parsed = DataProcessingConfiguration.model_validate(dataset_response)
        dataset_configs = defaultdict(list)
        for item in parsed.items:
            mapped_config = map_processing_config_item(item)
            dataset_configs[mapped_config.ts_id].append(mapped_config)
        return dataset_configs


class DatasetRepository:
    def __init__(self, api_router: MetadataRouter):
        self.api_router = api_router
        self._cache: dict[str, TimeSeriesContainer] = {}
        self._dependency_cache = set()
        self.resolved: dict[str, TimeSeriesContainer] = {}

    def fetch_root_datasets(
        self,
        network: str,
        sites: list[str],
        variables: list[str],
        periodicity: str,
    ) -> list[TimeSeriesContainer]:
        """Fetch processed dataset containers for the target sites and variables.

        Queries the metadata API for processed-level datasets matching the specified sites, variables, and resolution.
        Results are cached for efficient lookups.

        Args:
            network: The network identifier
            sites: List of site(s) to include.
            variables: List of variable(s) to include.
            periodicity: ISO 8601 duration string of the periodicity of the datasets.

        Returns:
            List of TimeSeriesContainer objects representing root datasets.
        """
        sites_params = [("originatingSite", f"{SITE_URI}/{network}-{site.lower()}") for site in sites]
        variables_params = [("sourceColumnName", f"{variable.upper()}") for variable in variables]
        other_params = [
            ("_view", "timeseries"),
            ("type.measure.aggregation.periodicity", periodicity),
            ("type.processingLevel", f"{PROCESSING_LEVEL_URI}/{ProcessingLevel.PROCESSED.value}"),
        ]

        response = self.api_router.fetch_dataset_by_params(tuple(sites_params + variables_params + other_params))
        all_containers = self._build_dataset_containers(response)
        return all_containers

    def fetch_dataset_dependencies(self, dataset_id: str) -> list[TimeSeriesContainer]:
        """Fetch all dependencies for a given dataset.

        Args:
            dataset_id: The dataset URI to fetch dependencies for.

        Returns:
            List of TimeSeriesContainer objects that the specified dataset depends on.
        """
        response = self.api_router.fetch_all_dependencies(extract_uri_id(dataset_id))
        all_containers = self._build_dataset_containers(response)
        return all_containers

    def fetch_dataset_by_id(self, dataset_id: str) -> TimeSeriesContainer:
        """Fetch a single dataset container by its ID.

        Checks the cache first before making an API call. Results are cached for subsequent lookups.

        Args:
            dataset_id: The dataset URI or ID to fetch.

        Returns:
            TimeSeriesContainer object for the requested dataset.
        """
        if dataset_id in self._cache:
            return self._cache[dataset_id]

        response = self.api_router.fetch_dataset_by_id(extract_uri_id(dataset_id))
        all_containers = self._build_dataset_containers(response)
        return all_containers[0]

    def _build_dataset_containers(self, dataset_response: dict[str, Any]) -> list[TimeSeriesContainer]:
        """Parse an API response container timeseries dataset items and convert them to the `TimeSeriesContainer`
        domain models.

        Cache each container so that later dependency-resolution steps can reuse them without repeated construction.

        Args:
            dataset_response: The JSON dictionary from the metadata API representing a set of dataset items.

        Returns:
            All mapped `TimeSeriesContainer` extracted from the response.
        """
        parsed = TimeSeriesDatasetResponse.model_validate(dataset_response)
        all_containers = []
        for item in parsed.items:
            container = map_dataset_item(item)
            self._cache[container.ts_id] = container
            all_containers.append(container)
        return all_containers

    def resolve_direct_dependencies(self, container: TimeSeriesContainer) -> None:
        """Resolve the direct dependencies for a dataset, using the `_all_dependencies` endpoint.

        The `_all_dependencies` endpoint is recursive, so we know that for all the "depends_on" datasets of the
        parent we will already have their direct dependencies.
        Keep a cache so that we can skip the API call for these child datasets

        Args:
            container: The dataset container whose dependencies are being resolved.
        """
        if container.ts_id in self._dependency_cache:
            return
        # The _all_dependencies endpoint is recursive, so we know that for all the "depends_on" datasets
        # of the parent we will already have their direct dependencies. Keep a cache so that we can skip
        # the API call for these child datasets
        self.fetch_dataset_dependencies(container.ts_id)
        self._dependency_cache.add(container.ts_id)
        self._dependency_cache.update(container.depends_on)

    def is_resolved(self, dataset_id: str) -> bool:
        """Determine if a dataset is resolved or not.

        Args:
            dataset_id: The dataset ID to check.

        Returns:
            True if the dataset is resolved, False otherwise.
        """
        return dataset_id in self.resolved

    def resolve(self, container: TimeSeriesContainer) -> None:
        """Resolve a dataset container by adding it to the resolved container

        Args:
            container: The dataset container of the resolved dataset.
        """
        self.resolved[container.ts_id] = container

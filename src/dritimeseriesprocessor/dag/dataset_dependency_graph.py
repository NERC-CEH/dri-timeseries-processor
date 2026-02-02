"""
Dataset dependency graph builder for time series processing.

This module provides functionality to build and resolve dependency directed acyclic graphs (DAGs) for time series
datasets. It fetches dataset metadata and processing configurations from an API, resolves dependencies recursively,
and constructs a complete dependency graph for specified sites and variables.

The graph enables downstream components to determine the full dependency chain for time series datasets,
giving knowledge of which datasets need to be processed before others.
"""

import logging
from collections import defaultdict
from graphlib import TopologicalSorter

from dritimeseriesprocessor.cli.selection import SelectionOption
from dritimeseriesprocessor.models.api_models.data_processing_configuration import DataProcessingConfiguration
from dritimeseriesprocessor.models.api_models.dataset_timeseries import TimeSeriesDatasetResponse
from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingConfig
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.models.mappers.api_to_domain import (
    map_dataset_item,
    map_processing_config_item,
    map_site_metadata,
)
from dritimeseriesprocessor.routers.metadata.metadata_router import MetadataRouter
from dritimeseriesprocessor.utils.enums import ProcessingLevel
from dritimeseriesprocessor.utils.urls import PROCESSING_LEVEL_URI

logger = logging.getLogger(__name__)


class DatasetDependencyGraph:
    """Builds a dataset dependency DAG for a given set of site(s), variable(s), and periodicities.

    If no sites / variables / periodicities provided, it will attempt to fetch all options from the metadata service.

    Orchestrates the construction of a complete dependency graph by fetching dataset metadata from an
    API, resolving dependencies recursively, and attaching processing configurations.

    The DAG is constructed recursively by:
        1. Fetching the target (processed) datasets (based on user input of site(s), variable(s), periodicity(s)).
        2. Fetching all relevant data processing configurations (QC, Infill, Correction, Aggregation, Derivation).
        3. Resolving dependencies of these data processing configurations
        4. Repeating for any new datasets introduced by these dependencies.
    """

    def __init__(self, metadata_router: MetadataRouter, network: str, selection: list[SelectionOption]):
        """Initialise the dependency graph builder.

        Args:
            metadata_router: A router object that handles metadata API calls.
            network: The network identifier
            selection: Selection specification for which datasets should be processed.
        """
        self.network = network
        self.selection = selection

        self.metadata_router = metadata_router
        self.datasets: dict[str, TimeSeriesContainer] = {}
        self.site_metadata: dict[str, SiteMetadata] = {}
        self._dataset_cache: dict[str, TimeSeriesContainer] = {}

    def build(self) -> None:
        """Build and return the complete dependency DAG for the specified sites, variables, and resolution

        This is the main entry point for building the dependency graph. It:
            1. Fetches root datasets matching the criteria
            2. Attaches data processing configurations (QC, Infill, Correction, Aggregation, Derivations)
            3. Recursively resolves all dependencies of these configurations
            4. Cleans up resources (caches and API connection)

        Handles recursion through a "batch" system where datasets are processed in iterative "batches" where each
        batch represents the current set of unresolved datasets. This approach enables data processing configuration
        lookups to be grouped into a single API call per batch, reducing network overhead and improving performance
        while preserving full dependency resolution.

        Each iteration performs the following steps:
            1. Fetch data processing configs (QC, infill, correction, aggregation, derivation) for all datasets in the
               current batch.
            2. All configuration objects (QC, infilling, correction) returned from the initial query in step (1) are
               attached to their corresponding `TimeSeriesContainer` objects.
            3. Create next batch out of any newly discovered datasets that are dependencies of the data processing
               config references

        The process continues until there are no new datasets left to resolve. This ensures that all datasets that
        we gather from the root datasets, direct dependencies, and data processing configurations will be resolved
        and represented in the final `self.datasets` object.
        """
        # Clear caches etc.
        self.reset()

        # Fetch the root datasets - i.e. the ones originally requested by the user.
        root_datasets = self._resolve_root_datasets()

        # Start the batch with the root datasets
        current_batch = {ds.ts_id: ds for ds in root_datasets}

        while current_batch:
            self._batch_start(current_batch)
            next_batch = {}

            # Fetch data processing configs for all IDs in the current batch - helps reduce number of API calls.
            batch_ids = [ts_id for ts_id in current_batch if ts_id not in self.datasets]
            configs_by_id = self._fetch_configs_for_dataset(batch_ids)

            # Resolve each dataset in the current batch
            for ts_id, container in current_batch.items():
                # If we've already seen this time series ID, we can skip
                if ts_id in self.datasets:
                    continue

                # Attach processing configs and find dependencies
                container.attach_configs(configs_by_id.get(container.ts_id, []))
                self._add_dependencies_to_batch(container, next_batch)

                # Once we're happy we have all the dependencies for this dataset, add it to our dataset container
                self.datasets[ts_id] = container

            # Do a bulk collection of dataset metadata for the next batch
            self._resolve_batch_datasets(next_batch)

            # move to next batch of recursion
            current_batch = next_batch

    @staticmethod
    def _batch_start(batch: dict[str, TimeSeriesContainer]) -> None:
        """A simple observability hook to capture the batch ids currently being processed.

        This method is mainly to give unit test something to hook into to test the current batch ids.

        Args:
            batch: Batch IDs being resolved
        """
        logger.debug(f"Resolving dataset ids: {list(batch.keys())}")

    def _add_dependencies_to_batch(
        self, container: TimeSeriesContainer, batch: dict[str, TimeSeriesContainer | None]
    ) -> None:
        """Add dataset dependencies into the next batch for resolution.

        For every dependency ID listed by the container (from metadata or configs):
            - If we have already seen this dataset, get its container from the cache
            - If we haven't already seen dataset, initialise the container as None to mark it as needing to be
              fetched from the metadata API

        Args:
            container: The dataset whose dependency IDs will be inspected.
            batch: The set that accumulates newly discovered datasets for the next iteration.
        """
        for dep_id in container.all_dependencies():
            if dep_id not in self.datasets and dep_id not in batch:
                if dep_id in self._dataset_cache:
                    batch[dep_id] = self._dataset_cache[dep_id]
                else:
                    # The dataset is required to be fetched from the metadata API.
                    # The reason for collecting them this way is so we can do a bulk API call for multiple datasets,
                    # rather than an individual API call. This saves a lot of time when many datasets are being
                    # processed.
                    # Any dataset ID with "None" as the dict value is processed in bulk by `_resolve_batch_datasets`
                    batch[dep_id] = None

    def _resolve_batch_datasets(self, batch: dict[str, TimeSeriesContainer | None]) -> None:
        """Resolve and fetch the datasets in the given batch of datasets.

        Fetches metadata from the dataset endpoint for all dataset IDs within the batch that does not currently have a
        TimeSeriesContainer (i.e. we haven't seen this dataset ID yet and so haven't retrieved its metadata)

        Args:
            batch: Batch IDs being resolved
        """
        ids_to_resolve = [batch_id for batch_id, c in batch.items() if c is None]
        if ids_to_resolve:
            response = self.metadata_router.fetch_dataset_by_ids(ids_to_resolve)
            all_containers = self._build_dataset_containers(response)
            for dep_container in all_containers:
                batch[dep_container.ts_id] = dep_container

    def _resolve_root_datasets(self) -> list[TimeSeriesContainer]:
        """Resolve and fetch the root datasets for the selection of datasets requested.

        Uses the list of SelectionOption objects, that represent either:
            - a fully-specified dataset request (explicit selection), or
            - a partially-specified constraint (cross-product selection)

        Site metadata is fetched up-front for all requested sites. If any query leaves the site dimension unconstrained,
        site metadata is fetched for all sites in the network.

        For each query, datasets are fetched using the available constraints. Any unconstrained dimensions
        (variables or periodicities) are expanded downstream during the metadata API call.

        Returns:
            TimeSeriesContainer objects representing the root datasets from which dependency resolution will proceed.
        """
        # Determine which sites we need to fetch metadata for
        requested_sites = set()
        for query in self.selection:
            if not query.sites:
                # If no site provided, we know we need to fetch all, so break early
                break
            requested_sites.update(query.sites)

        all_site_ids = self._fetch_site_metadata(list(requested_sites))

        containers = set()
        for query in self.selection:
            containers.update(
                self._fetch_root_datasets(query.sites or all_site_ids, query.variables or [], query.periodicities or [])
            )

        return list(containers)

    def _fetch_root_datasets(
        self, sites: list[str], variables: list[str], periodicities: list[str]
    ) -> list[TimeSeriesContainer]:
        """Fetch processed dataset containers for the target sites and variables.

        Queries the metadata API for processed-level datasets matching the specified sites, variables, and resolution.
        Results are cached for efficient lookups.

        Returns:
            List of TimeSeriesContainer objects representing root datasets.
        """
        sites_params = [("originatingSite", site) for site in sites]
        variables_params = [("sourceColumnName", variable) for variable in variables]
        periodicity_params = [("measure.aggregation.periodicity", periodicity) for periodicity in periodicities]
        other_params = [
            ("_view", "timeseries"),
            ("processingLevel", f"{PROCESSING_LEVEL_URI}/{ProcessingLevel.PROCESSED.value}"),
        ]

        response = self.metadata_router.fetch_dataset_by_params(
            tuple(sites_params + variables_params + periodicity_params + other_params)
        )
        all_containers = self._build_dataset_containers(response)

        # FOR TESTING: intercept API and override metadata. DERIVATION -> AGGREGATION
        # from dritimeseriesprocessor.utils.enums import MethodType

        # wd = all_containers[0]
        # wd.method.method_type = MethodType.AGGREGATION
        # wd.method.name = "agg_daily_wd"

        return all_containers

    def _fetch_configs_for_dataset(self, dataset_ids: list[str]) -> dict[str, list[DataProcessingConfig]]:
        """Fetch data processing configurations (QC, infilling, correction) that apply to the specified dataset(s).

        Args:
            dataset_ids: Single dataset ID or list of dataset IDs.

        Returns:
            Dictionary mapping dataset IDs to their list of processing configurations.
        """
        if not dataset_ids:
            return {}

        response = self.metadata_router.fetch_processing_configs(dataset_ids)
        dataset_configs = self._build_processing_configs(response)
        return dataset_configs

    def _fetch_site_metadata(self, sites: list[str] | None = None) -> list[str]:
        """Fetches site metadata for all sites with variables being processed. Sets the `self.sites_metadata` dict.

        Args:
            sites: Select sites to get metadata for.  If empty, will fetch all sites for given network.

        Returns:
            List of Metadata API site IDs
        """
        if not sites:
            # If no sites provided, find all sites for the given network
            logger.warning(f"No sites provided. Fetching all sites for: {self.network}")
            network_response = self.metadata_router.fetch_network(self.network)
            sites = [site.id for site in network_response.items[0].contains]

        sites_response = self.metadata_router.fetch_sites(sites)

        fetched_site_ids = []
        for item in sites_response.items:
            meta = map_site_metadata(item)
            self.site_metadata[meta.site_id] = meta
            fetched_site_ids.append(meta.site_id)
        return fetched_site_ids

    def _build_dataset_containers(self, dataset_response: TimeSeriesDatasetResponse) -> list[TimeSeriesContainer]:
        """Parse an API response container timeseries dataset items and convert them to the `TimeSeriesContainer`
        domain models.

        Cache each container so that later dependency-resolution steps can reuse them without repeated construction.

        Args:
            dataset_response: The TimeSeriesDatasetResponse representing a set of dataset items.

        Returns:
            All mapped `TimeSeriesContainer` extracted from the response.
        """
        all_containers = []
        for item in dataset_response.items:
            container = map_dataset_item(item, self.site_metadata)
            self._dataset_cache[container.ts_id] = container
            all_containers.append(container)
        return all_containers

    def _build_processing_configs(
        self, dataset_response: DataProcessingConfiguration
    ) -> dict[str, list[DataProcessingConfig]]:
        """Parse an API response containing processing configuration items and return them grouped by timeseries ID.

        Args:
            dataset_response: The DataProcessingConfig representing a set of processing configs.

        Returns:
            A dictionary keyed by timeseries ID, with value as the list of associated processing configs.
        """
        dataset_configs = defaultdict(list)
        for item in dataset_response.items:
            mapped_config = map_processing_config_item(item, self.site_metadata)
            dataset_configs[mapped_config.ts_id].append(mapped_config)
        return dataset_configs

    def build_dag(self) -> dict[str, list[str]]:
        """Construct the DAG structure from resolved datasets.

        Returns:
           A dictionary mapping dataset IDs to lists of dependent dataset IDs.
        """
        dag = {container_id: container.all_dependencies() for container_id, container in self.datasets.items()}
        # ensure all nodes exist as keys
        for ds_id in list(dag):
            for dep in dag[ds_id]:
                dag.setdefault(dep, [])
        return dag

    def flat_topo_sort(self) -> list[str]:
        """Return a flat topological ordering of the DAG."""
        topo_sorter = TopologicalSorter(self.build_dag())
        layers = topo_sorter.static_order()  # Raises a CycleError if cycle detected in the DAG
        return list(layers)

    def layered_topo_sort(self) -> list[list[str]]:
        """Return a layered (batched) topological ordering of the DAG.

        Each inner list contains dataset IDs that can be processed in parallel, given that all their dependencies
        appear in earlier layers.

        Raises:
            ValueError: If the dependency graph contains a cycle.
        """
        layers = []
        topo_sorter = TopologicalSorter(self.build_dag())
        topo_sorter.prepare()  # Raises a CycleError if cycle detected in the DAG

        while topo_sorter.is_active():
            ready = list(topo_sorter.get_ready())
            ready.sort()
            layers.append(ready)
            topo_sorter.done(*ready)

        return layers

    def reset(self) -> None:
        """Clear all cached and resolved datasets states."""
        self._dataset_cache.clear()
        self.datasets.clear()
        self.site_metadata.clear()

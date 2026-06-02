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
from datetime import datetime
from graphlib import TopologicalSorter

from dritimeseriesprocessor.cli.selection import DatasetIdSelection, DimensionSelection, Selection
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
from dritimeseriesprocessor.utils.urls import PLATFORM_URI, PROCESSING_LEVEL_URI

logger = logging.getLogger(__name__)


class DatasetDependencyGraph:
    """Builds a dataset dependency DAG for a given set of site(s), variable(s), and periodicities.

    If no sites / variables / periodicities provided, it will attempt to fetch all options from the metadata service.
    A start and end date can be optionally provided, which can limit the sites that are fetched from the metadata
    service to those that are operational during that given window.

    Orchestrates the construction of a complete dependency graph by fetching dataset metadata from an
    API, resolving dependencies recursively, and attaching processing configurations.

    The DAG is constructed recursively by:
        1. Fetching the target (processed) datasets (based on user input of site(s), variable(s), periodicity(s)).
        2. Fetching all relevant data processing configurations (QC, Infill, Correction, Aggregation, Derivation).
        3. Resolving dependencies of these data processing configurations
        4. Repeating for any new datasets introduced by these dependencies.
    """

    def __init__(
        self,
        metadata_router: MetadataRouter,
        selection: list[Selection],
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ):
        """Initialise the dependency graph builder.

        Args:
            metadata_router: A router object that handles metadata API calls.
            selection: Selection specification for which datasets should be processed.
            start_date: Start of the date window to check for operational sites  (inclusive).
            end_date: End of the date window to check for operational sites (inclusive).
        """
        self.selection = selection
        self.start_date = start_date
        self.end_date = end_date

        self.metadata_router = metadata_router
        self.datasets: dict[str, TimeSeriesContainer] = {}
        self.site_metadata: dict[str, SiteMetadata] = {}

        self._dep_ts_ids: set[str] = set()
        self._load_dep_ts_ids: set[str] = set()

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
            # Load-only deps are excluded: we don't fetch their configs or resolve their dependencies.
            batch_ids = [
                ts_id for ts_id in current_batch if ts_id not in self.datasets and not self._is_load_only(ts_id)
            ]
            configs_by_id = self._fetch_configs_for_dataset(batch_ids)

            # Resolve each dataset in the current batch
            for ts_id, container in current_batch.items():
                # If we've already seen this time series ID, we can skip
                if ts_id in self.datasets:
                    continue

                # Load-only deps are flagged as load_only and added without fetching configs or resolving dependencies
                if self._is_load_only(ts_id):
                    container.load_only = True
                    self.datasets[ts_id] = container
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

    def _is_load_only(self, ts_id: str) -> bool:
        """Return True if a dataset should be loaded but not processed.

        A dataset is treated as load-only when it has been referenced via `load_dep_ts` but never via `dep_ts`.
        If both references exist, full processing (`dep_ts`) takes priority.

        Args:
            ts_id: The dataset ID to check.

        Returns:
            True if the dataset should be loaded but not processed or saved.
        """
        return ts_id in self._load_dep_ts_ids and ts_id not in self._dep_ts_ids

    def _add_dependencies_to_batch(
        self, container: TimeSeriesContainer, batch: dict[str, TimeSeriesContainer | None]
    ) -> None:
        """Add dataset dependencies into the next batch for resolution.

        For every dependency ID listed by the container (from metadata or configs):
            - Classifies the dep as either a full-processing dep (dep_ts) or load-only dep (load_dep_ts).
            - If already resolved as load-only but now encountered via "dep_ts", pulls it back out of
              self.datasets and re-queues it so it gets full config fetching and dependency resolution.
            - If not yet seen, queues it for the next batch (using the cache if available, otherwise marking it
              as None so it gets fetched from the metadata API in bulk).

        Args:
            container: The dataset whose dependency IDs will be inspected.
            batch: The dict that accumulates newly discovered datasets for the next iteration.
        """
        load_only_deps = set(container.load_only_dependencies())
        for dep_id in container.all_dependencies():
            # Classify the reference - dep_ts always wins over load_dep_ts if both are seen
            if dep_id in load_only_deps:
                self._load_dep_ts_ids.add(dep_id)
            else:
                self._dep_ts_ids.add(dep_id)

            # If we already resolved this dep as load-only in an earlier batch but now have a full dep_ts
            # reference to it, we need to redo it properly. Pull it back out and re-queue it - it will go
            # through config fetching and dependency resolution in the next iteration like any normal dep.
            if dep_id in self.datasets and self.datasets[dep_id].load_only and not self._is_load_only(dep_id):
                re_queued = self.datasets.pop(dep_id)
                re_queued.load_only = False
                batch[dep_id] = re_queued

            elif dep_id not in self.datasets and dep_id not in batch:
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

        Dispatches on selection type:
        - `DimensionSelection`: queries by site/variable/periodicity dimensions. Site metadata is
          fetched up-front; if `sites` is None, all sites for the selection's network are fetched.
        - `DatasetIdSelection`: fetches datasets directly by ID, with site metadata resolved lazily.

        Returns:
            TimeSeriesContainer objects representing the root datasets from which dependency resolution will proceed.
        """
        containers: set[TimeSeriesContainer] = set()

        for query in self.selection:
            if isinstance(query, DatasetIdSelection):
                containers.update(self._fetch_root_datasets_by_ids(query.dataset_ids))
            elif isinstance(query, DimensionSelection):
                sites = self._fetch_site_metadata(query.sites or [], network=query.network)
                containers.update(self._fetch_root_datasets(sites, query.variables or [], query.periodicities or []))
            else:
                raise ValueError(f"Unsupported selection type in dependency graph: {type(query).__name__}")

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

    def _fetch_root_datasets_by_ids(self, dataset_ids: list[str]) -> list[TimeSeriesContainer]:
        """Fetch root dataset containers for an explicit list of dataset IDs.

        Site metadata is resolved lazily inside `_build_dataset_containers`.

        Args:
            dataset_ids: Dataset IDs to fetch.

        Returns:
            List of TimeSeriesContainer objects.
        """
        response = self.metadata_router.fetch_dataset_by_ids(dataset_ids)
        return self._build_dataset_containers(response)

    def _fetch_site_metadata(self, site_ids: list[str], network: str | None = None) -> list[str]:
        """Fetches site metadata for all sites with variables being processed. Sets the `self.sites_metadata` dict.

        Args:
            site_ids: Select sites to get metadata for. If empty, fetches all sites for `network`.
            network: Network identifier used when `site_ids` is empty.

        Returns:
            List of Metadata API site IDs
        """
        if not site_ids:
            if network is None:
                raise ValueError("network must be provided when no site_ids are specified")
            logger.warning(f"No sites provided. Fetching all sites for: {network}")
            sites_response = self.metadata_router.fetch_sites_by_network(network)
        else:
            sites_response = self.metadata_router.fetch_sites(site_ids)

        fetched_site_ids = []
        for item in sites_response.items:
            meta = map_site_metadata(item)
            # Filter sites to only those that are "active".  By default, if start and end date not provide, all sites
            # are considered active.
            if meta.is_active(window_start=self.start_date, window_end=self.end_date):
                self.site_metadata[meta.site_id] = meta
                fetched_site_ids.append(meta.site_id)
        return fetched_site_ids

    def _fetch_missing_site_metadata(self, site_ids: list[str]) -> list[str]:
        """Fetch and cache site metadata for any site IDs not yet in `self.site_metadata`.

        Unlike `_fetch_site_metadata`, this does not apply the `is_active` date window filter -
        dependency sites are required regardless of operational status.

        Args:
            site_ids: Site IDs to ensure metadata is available for.

        Returns:
            List of Metadata API site IDs
        """
        missing_site_ids = [site_id for site_id in site_ids if site_id not in self.site_metadata]
        if not missing_site_ids:
            return []

        logger.info(f"Fetching metadata for dependent sites: {missing_site_ids}")
        sites_response = self.metadata_router.fetch_sites(missing_site_ids)

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
        # Dedupe site_ids in case multiple datasets reference the same missing site
        site_ids = list({item.originating_site[0].id for item in dataset_response.items if item.originating_site})
        self._fetch_missing_site_metadata(site_ids)

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
            self._get_deployment_attributes(mapped_config)
            dataset_configs[mapped_config.ts_id].append(mapped_config)
        return dataset_configs

    def _get_deployment_attributes(self, mapped_config: DataProcessingConfig) -> None:
        """Some processing configs will have a special "deployment attribute" parameter. This is used to fetch
        a specific bit of metadata from the sensor deployment. This method resolves that metadata fetching and
        attaches it as a specific parameter value to the method config.

        Args:
            mapped_config: Data processing configuration that may have deployment attribute to resolve
        """
        for method_config in mapped_config.method_configs:
            for param, value in method_config.params.items():
                if isinstance(value, dict) and value.get(f"{param}.source", "") == "deployment":
                    platform = value[f"{param}.platform"]
                    attribute = value[f"{param}.attribute"]

                    # Send this to the deployment API endpoint to get the value of the requested attribute
                    platform_id = f"{PLATFORM_URI}/{platform}"
                    deployment_info = self.metadata_router.fetch_deployment_by_platform(platform_id)

                    attribute_values = []
                    for deployment in deployment_info.items:
                        start_date = deployment.start_date
                        end_date = deployment.end_date
                        attribute_value = getattr(deployment, attribute)
                        attribute_values.append((start_date, end_date, attribute_value))

                    value[f"{param}.value"] = attribute_values

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
        self._dep_ts_ids.clear()
        self._load_dep_ts_ids.clear()

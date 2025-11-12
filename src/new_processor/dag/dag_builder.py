"""
Dataset dependency graph builder for time series processing.

This module provides functionality to build and resolve dependency directed acyclic graphs (DAGs) for time series
datasets. It fetches dataset metadata and processing configurations from an API, resolves dependencies recursively,
and constructs a complete dependency graph for specified sites and variables.

The graph enables downstream components to determine the full dependency chain for time series datasets,
giving knowledge of which datasets need to be processed before others.
"""

from collections import defaultdict

from new_processor.api_models.data_processing_configuration import DataProcessingConfiguration
from new_processor.api_models.dataset_dependencies import DatasetDependencies
from new_processor.api_models.dataset_timeseries import TimeSeriesDataset
from new_processor.domain_models.processing_config import ProcessingConfig
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.externals.routers import MetadataRouter
from new_processor.mappers.api_to_domain import map_dataset_item, map_processing_config_item
from new_processor.utils.enums import ConfigurationType, ProcessingLevel
from new_processor.utils.strings import extract_uri_id
from new_processor.utils.urls import CONFIGURATION_TYPE_URI, PROCESSING_LEVEL_URI, SITE_URI


class DatasetDependencyGraph:
    """
    Builds a dataset dependency DAG for a given set of site(s), variable(s), and resolution.

    This class orchestrates the construction of a complete dependency graph by fetching dataset metadata from an
    API, resolving dependencies recursively, and attaching processing configurations.

    The DAG is constructed recursively by:
        1. Fetching the target (processed) datasets (based on user input of site(s), variable(s), resolution).
        2. Resolving direct dependencies via the `_all_dependencies.json` endpoint.
        3. Fetching all relevant data processing configurations (QC, Infill, Correction).
        4. Repeating for any new datasets introduced by these direct dependencies and configuration dependencies.
    """

    def __init__(
        self,
        network: str,
        sites: str | list[str],
        variables: str | list[str],
        periodicity: str,
        api_router: MetadataRouter,
    ):
        """Initialize the dependency graph builder.

        Args:
            network: The network identifier
            sites: List of site(s) to include.
            variables: List of variable(s) to include.
            periodicity: ISO 8601 duration string of the periodicity of the datasets.
            api_router: A router object that handles API calls.
        """
        self.network = network
        self.sites = [sites] if isinstance(sites, str) else sites
        self.variables = [variables] if isinstance(variables, str) else variables
        self.periodicity = periodicity

        self.api_router = api_router
        self.datasets: dict[str, TimeSeriesContainer] = {}
        self._dataset_cache: dict[str, TimeSeriesContainer] = {}

    def _fetch_root_datasets(self) -> list[TimeSeriesContainer]:
        """Fetch processed dataset containers for the target sites and variables.

        Queries the metadata API for processed-level datasets matching the specified
        sites, variables, and resolution. Results are cached for efficient lookups.

        Returns:
            List of TimeSeriesContainer objects representing root datasets.
        """
        sites_params = [("originatingSite", f"{SITE_URI}/{self.network}-{site.lower()}") for site in self.sites]
        variables_params = [("sourceColumnName", f"{variable.upper()}") for variable in self.variables]
        other_params = [
            ("_view", "timeseries"),
            ("type.measure.aggregation.periodicity", self.periodicity),
            ("type.processingLevel", f"{PROCESSING_LEVEL_URI}/{ProcessingLevel.PROCESSED.value}"),
        ]

        response = self.api_router.fetch_dataset_by_params(tuple(sites_params + variables_params + other_params))
        parsed = TimeSeriesDataset.model_validate(response)

        all_containers = []
        for item in parsed.items:
            container = map_dataset_item(item)
            self._dataset_cache[container.ts_id] = container
            all_containers.append(container)
        return all_containers

    def _fetch_dataset_dependencies(self, dataset_id: str) -> list[TimeSeriesContainer]:
        """Fetch all dependencies for a given dataset.

        Args:
            dataset_id: The dataset URI to fetch dependencies for.

        Returns:
            List of TimeSeriesContainer objects that the specified dataset depends on.
        """
        response = self.api_router.fetch_all_dependencies(extract_uri_id(dataset_id))
        parsed = DatasetDependencies.model_validate(response)

        all_containers = []
        for item in parsed.items:
            container = map_dataset_item(item)
            self._dataset_cache[container.ts_id] = container
            all_containers.append(container)
        return all_containers

    def _fetch_dataset_by_id(self, dataset_id: str) -> TimeSeriesContainer:
        """Fetch a single dataset container by its ID.

        Checks the cache first before making an API call. Results are cached for subsequent lookups.

        Args:
            dataset_id: The dataset URI or ID to fetch.

        Returns:
            TimeSeriesContainer object for the requested dataset.
        """
        if dataset_id in self._dataset_cache:
            return self._dataset_cache[dataset_id]

        response = self.api_router.fetch_dataset_by_id(extract_uri_id(dataset_id))
        parsed = TimeSeriesDataset.model_validate(response)
        container = map_dataset_item(parsed.items[0])
        self._dataset_cache[container.ts_id] = container
        return container

    def _fetch_configs_for_dataset(self, dataset_id: str | list[str]) -> dict[str, list[ProcessingConfig]]:
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
        parsed = DataProcessingConfiguration.model_validate(response)

        dataset_configs = defaultdict(list)
        for item in parsed.items:
            mapped_config = map_processing_config_item(item)
            dataset_configs[mapped_config.ts_id].append(mapped_config)

        return dataset_configs

    def build(self) -> None:
        """Build and return the complete dependency DAG for the specified sites, variables, and resolution

        This is the main entry point for building the dependency graph. It:
        1. Fetches root datasets matching the criteria
        2. Recursively resolves all dependencies
        3. Attaches data processing configurations (QC, Infill, Correction)
        4. Cleans up resources (caches and API connection)
        """
        root_datasets = self._fetch_root_datasets()
        self._resolve_dataset(root_datasets)

        # clear the cache
        self._dataset_cache = {}

    def _resolve_dataset(self, root_datasets: list[TimeSeriesContainer]) -> None:
        """Recursively resolve dependencies for all datasets.

        Handles recursion through a "batch" system where datasets are processed in iterative "batches" where each
        batch represents the current set of unresolved datasets. This approach enables data processing configuration
        lookups to be grouped into a single API call per batch, reducing network overhead and improving performance
        while preserving full dependency resolution.

        Each iteration performs the following steps:
        1. Fetch data processing configs (QC, infill, correction) for all datasets in the current batch.
        2. For each dataset in current batch, get direct dependencies from the `_all_dependencies` API endpoint.
        3. All configuration objects (QC, infilling, correction) returned from the initial query in step (1) are
           attached to their corresponding `TimeSeriesContainer` objects.
        4. Create next batch out of any newly discovered datasets (from either direct dependencies or
           data processing config references)

        The process continues until there are no new datasets left to resolve. This ensures that all datasets that
        we gather from the root datasets, direct dependencies, and data processing configurations will be resolved
        and represented in the final `self.datasets` object.

        Args:
            root_datasets: List of root-level datasets to act as the starting batch.
        """
        current_batch = list(root_datasets)
        resolved = set()  # keep a log of which IDs have been resolved
        dependency_cache = set()  # keep a log which IDs we know we have got direct dependencies for

        while current_batch:
            next_batch = []

            # Fetch data processing configs for all IDs in the current batch - helps reduce number of API calls.
            batch_ids = [ds.ts_id for ds in current_batch if ds.ts_id not in resolved]
            configs_by_id = self._fetch_configs_for_dataset(batch_ids)

            # Resolve each dataset in the current batch
            for container in current_batch:
                # If we've already seen this time series ID, we can skip
                if container.ts_id in resolved:
                    continue
                resolved.add(container.ts_id)
                self.datasets[container.ts_id] = container

                # Resolve direct dataset dependencies
                if container.ts_id not in dependency_cache:
                    # The _all_dependencies endpoint is recursive, so we know that for all the "depends_on" datasets
                    # of the parent we will already have their direct dependencies. Keep a cache so that we can skip
                    # the API call for these child datasets
                    self._fetch_dataset_dependencies(container.ts_id)
                    dependency_cache.add(container.ts_id)
                    dependency_cache.update(container.depends_on)

                # Attach the data processing configs
                for config in configs_by_id.get(container.ts_id, []):
                    if config.config_type == ConfigurationType.QUALITY_CONTROL:
                        container.qc_configs.append(config)
                    elif config.config_type == ConfigurationType.INFILLING:
                        container.infill_configs.append(config)
                    elif config.config_type == ConfigurationType.CORRECTION:
                        container.correction_configs.append(config)
                    else:
                        raise TypeError(f"Unknown configuration type: {config.config_type}")

                # Recurse through all known dependencies - adding items to the next batch
                for dep_id in container.all_dependencies():
                    if dep_id not in self.datasets:
                        dep_container = self._fetch_dataset_by_id(dep_id)
                        self.datasets[dep_id] = dep_container
                        next_batch.append(dep_container)

            current_batch = next_batch  # move to next batch of recursion

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

#
# import time
#
# router = MetadataRouter(app_config.metadata_api_url)
# start = time.time()
# builder = DatasetDependencyGraph("cosmos", sites=["BUNNY"], variables=["RN"], periodicity="PT30M", api_router=router)
#
# builder.build()
# DAG = builder.build_dag()
# end = time.time()
# print("DAG built took {} seconds".format(end - start))
#
# print("\n=== DAG ===")
# for idx, (node, deps) in enumerate(DAG.items()):
#     print(idx, f"{node} -> {[d for d in deps]}")

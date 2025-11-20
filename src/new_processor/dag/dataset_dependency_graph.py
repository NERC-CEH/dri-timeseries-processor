"""
Dataset dependency graph builder for time series processing.

This module provides functionality to build and resolve dependency directed acyclic graphs (DAGs) for time series
datasets. It fetches dataset metadata and processing configurations from an API, resolves dependencies recursively,
and constructs a complete dependency graph for specified sites and variables.

The graph enables downstream components to determine the full dependency chain for time series datasets,
giving knowledge of which datasets need to be processed before others.
"""

from new_processor.dag.batch import Batch
from new_processor.dag.repositories import ConfigRepository, DatasetRepository
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.externals.routers import MetadataRouter


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

        self.dataset_repository = DatasetRepository(api_router)
        self.config_repository = ConfigRepository(api_router)

    def build(self) -> None:
        """Build and return the complete dependency DAG for the specified sites, variables, and resolution

        This is the main entry point for building the dependency graph. It:
        1. Fetches root datasets matching the criteria
        2. Recursively resolves all dependencies
        3. Attaches data processing configurations (QC, Infill, Correction)
        4. Cleans up resources (caches and API connection)
        """
        root_datasets = self.dataset_repository.fetch_root_datasets(
            self.network, self.sites, self.variables, self.periodicity
        )
        self._resolve_datasets(root_datasets)

    def _resolve_datasets(self, root_datasets: list[TimeSeriesContainer]) -> None:
        """Recursively resolve dependencies for all datasets.

        Handles recursion through a "batch" system where datasets are processed in iterative "batches" where each
        batch represents the current set of uns datasets. This approach enables data processing configuration
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
        self.dataset_repository.reset()
        batch = Batch(root_datasets, self.dataset_repository)

        while not batch.empty():
            # Fetch data processing configs for all IDs in the current batch - helps reduce number of API calls.
            batch_ids = [ts_id for ts_id in batch.current if not self.dataset_repository.is_resolved(ts_id)]
            configs_by_id = self.config_repository.fetch_configs_for_dataset(batch_ids)

            # Resolve each dataset in the current batch
            for ts_id, container in batch.current.items():
                # If we've already seen this time series ID, we can skip
                if self.dataset_repository.is_resolved(ts_id):
                    continue

                # Perform the resolving operations
                self.dataset_repository.resolve_direct_dependencies(container)
                container.attach_configs(configs_by_id.get(container.ts_id, []))
                batch.add_dependencies_to_next_batch(container)

                # Once we're happy this dataset has been fully resolved, add it to our resolved dataset container
                self.dataset_repository.resolve(container)

            batch.advance()  # move to next batch of recursion

    def build_dag(self) -> dict[str, list[str]]:
        """Construct the DAG structure from resolved datasets.

        Returns:
           A dictionary mapping dataset IDs to lists of dependent dataset IDs.
        """
        dag = {
            container_id: container.all_dependencies()
            for container_id, container in self.dataset_repository.resolved.items()
        }
        # ensure all nodes exist as keys
        for ds_id in list(dag):
            for dep in dag[ds_id]:
                dag.setdefault(dep, [])
        return dag

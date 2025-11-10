from collections import defaultdict

from driutils.metadata_api.api_manager import MetadataAPIManager

from dritimeseriesprocessor.configuration import app_config
from new_processor.api_models.dataset_timeseries import TimeSeriesDataset
from new_processor.api_models.dataset_dependencies import DatasetDependencies
from new_processor.api_models.data_processing_configuration import DataProcessingConfiguration
from new_processor.mappers.api_to_domain import map_dataset_item, map_processing_config_item
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.domain_models.processing_config import ProcessingConfig
from new_processor.utils.urls import ID_URI, REF_URI, SITE_URI, PROCESSING_LEVEL_URI
from new_processor.utils.enums import ProcessingLevel
from new_processor.utils.strings import extract_uri_id
from new_processor.dag.routers import MetadataRouter


class DatasetDependencyGraph:
    """Builds a dataset dependency DAG for a given (site, variables, resolution) set."""

    def __init__(self, network: str, sites: list[str], variables: list[str], resolution: str):
        self.network = network
        self.sites = sites
        self.variables = variables
        self.resolution = resolution

        self.api_router = MetadataRouter(host=app_config.metadata_api_url, network=network)

        self.dag: dict[str, list[str]] = {}
        self.datasets: dict[str, TimeSeriesContainer] = {}

        self._dataset_cache: dict[str, TimeSeriesContainer] = {}
        self._dependency_cache: list[str] = []

    async def build(self) -> dict[str, list[str]]:
        """Build and store the DAG for the specified sites, variables, and resolution."""
        root_datasets = await self._fetch_root_datasets()
        for container in root_datasets:
            await self._resolve_dataset(container)
        return self.dag

    async def _fetch_root_datasets(self) -> list[TimeSeriesContainer]:
        """Fetch processed datasets for the target sites/variables."""
        if isinstance(self.sites, str):
            self.sites = [self.sites]

        if isinstance(self.variables, str):
            self.variables = [self.variables]

        sites_params = [("originatingSite", f"{SITE_URI}/{self.network}-{site.lower()}") for site in self.sites]
        variables_params = [("sourceColumnName", f"{variable.upper()}") for variable in self.variables]
        other_params = [
            ("_view", "timeseries"),
            ("type.measure.aggregation.periodicity", self.resolution),
            ("type.processingLevel", f"{PROCESSING_LEVEL_URI}/{ProcessingLevel.PROCESSED.value}"),
        ]

        response = await self.api_router.fetch_dataset_by_params(sites_params + variables_params + other_params)
        parsed = TimeSeriesDataset.model_validate(response)
        
        all_containers = []
        for item in parsed.items:
            container = map_dataset_item(item)
            self._dataset_cache[container.ts_id] = container
            all_containers.append(container)
        return all_containers

    async def _fetch_dataset_dependencies(self, dataset_id) -> list[TimeSeriesContainer]:
        response = await self.api_router.fetch_all_dependencies(extract_uri_id(dataset_id))
        parsed = DatasetDependencies.model_validate(response)

        all_containers = []
        for item in parsed.items:
            container = map_dataset_item(item)
            self._dataset_cache[container.ts_id] = container
            all_containers.append(container)
        return all_containers

    async def _fetch_dataset_by_id(self, dataset_id) -> TimeSeriesContainer:
        response = await self.api_router.fetch_dataset_by_id(extract_uri_id(dataset_id))
        parsed = TimeSeriesDataset.model_validate(response)
        container = map_dataset_item(parsed.items[0])
        self._dataset_cache[container.ts_id] = container
        return container

    async def _resolve_dataset(self, container: TimeSeriesContainer) -> None:
        """Recursively resolve dependencies for a given dataset ID."""
        if container.ts_id in self.datasets:
            return  # Already resolved
        self.datasets[container.ts_id] = container

        # 1) Instance-ready deps from _all_dependencies.json
        if container.ts_id not in self._dependency_cache:
            await self._fetch_dataset_dependencies(container.ts_id)
            # The _all_dependencies endpoint is recursive, so we know that for all the "depends_on" datasets of the
            # parent we will already have their direct dependencies. Keep a cache so that we can skip the API call for
            # these child datasets
            self._dependency_cache.extend(container.depends_on)

        # 2) Get processing configs for this dataset (correction, QC, infill) (only needed for RAW datasets)
        #container.configs = await self.fetch_configs_for_dataset(container.ts_id)

        # 3) Recurse into dependencies
        for dep_id in container.all_dependencies():
            if dep_id not in self.datasets:
                dep_container = await self._fetch_dataset_by_id(dep_id)
                await self._resolve_dataset(dep_container)

    #
    #
    #
    #
    #
    #
    #
    # async def _get_dataset(self, dataset_id: str) -> TimeSeriesContainer:
    #     if dataset_id in self._dataset_cache:
    #         return self._dataset_cache[dataset_id]
    #     response = await self.router.fetch_dataset([("@id", dataset_id)])
    #     parsed = TimeSeriesDataset.model_validate(response)
    #     dataset = map_dataset_item(parsed.items[0])
    #     self._dataset_cache[dataset_id] = dataset
    #     return dataset
    #
    # async def _fetch_dependencies(self, dataset_id: str) -> list[str]:
    #     if dataset_id in self._dependency_cache:
    #         return self._dependency_cache[dataset_id]
    #     response = await self.router.fetch_dependencies(dataset_id)
    #     parsed = DatasetDependencies.model_validate(response)
    #     deps = [item.id for item in parsed.items]
    #     self._dependency_cache[dataset_id] = deps
    #     return deps
    #
    # async def _fetch_processing_configs(self, dataset_id: str) -> list[ProcessingConfig]:
    #     response = await self.router.fetch_processing_configs(dataset_id)
    #     parsed = DataProcessingConfiguration.model_validate(response)
    #     return [map_processing_config_item(item) for item in parsed.items]


builder = DatasetDependencyGraph(
    "cosmos",
    sites=["BUNNY"],
    variables=["RN"],
    resolution="PT30M",
)
import asyncio
a = asyncio.run(builder.build())

for _ in builder.datasets:
    print(_)

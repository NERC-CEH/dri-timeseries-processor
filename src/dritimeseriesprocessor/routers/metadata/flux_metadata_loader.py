"""Load local EddyPro metadata into graph-ready domain objects."""

from __future__ import annotations

from dataclasses import dataclass

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingConfig
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.models.mappers.api_to_domain import (
    map_dataset_item,
    map_processing_config_item,
    map_site_metadata,
)
from dritimeseriesprocessor.routers.metadata.local_eddypro_metadata_source import LocalEddyProMetadataSource


@dataclass(frozen=True)
class LocalFluxGraphData:
    datasets: dict[str, TimeSeriesContainer]
    site_metadata: dict[str, SiteMetadata]


class FluxMetadataLoader:
    """Build local graph data from the EddyPro fixtures."""

    def __init__(self, network: str, sites: list[str] | None) -> None:
        self._source = LocalEddyProMetadataSource(network=network, sites=sites)

    def load(self) -> LocalFluxGraphData:
        fixture_set = self._source.load()

        site_metadata = {site.site_id: site for site in (map_site_metadata(item) for item in fixture_set.sites.items)}

        datasets = {
            dataset.ts_id: dataset
            for dataset in (map_dataset_item(item, site_metadata) for item in fixture_set.datasets.items)
        }

        processing_configs = [
            map_processing_config_item(item, site_metadata) for item in fixture_set.processing_configs.items
        ]
        processing_configs_by_dataset = self._group_processing_configs(processing_configs)

        for dataset_id, configs in processing_configs_by_dataset.items():
            if dataset_id not in datasets:
                continue
            datasets[dataset_id].attach_configs(configs)

        return LocalFluxGraphData(datasets=datasets, site_metadata=site_metadata)

    @staticmethod
    def _group_processing_configs(configs: list[DataProcessingConfig]) -> dict[str, list[DataProcessingConfig]]:
        grouped: dict[str, list[DataProcessingConfig]] = {}
        for config in configs:
            grouped.setdefault(config.ts_id, []).append(config)
        return grouped

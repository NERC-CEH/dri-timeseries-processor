"""
Local metadata loader for EddyPro / flux processing.

Provides access to flux site metadata, dataset definitions, and EddyPro-specific configuration
from local JSON fixtures. Produces the same domain model objects (TimeSeriesContainer, SiteMetadata,
DataProcessingConfig) that the real MetadataRouter + DAG builder would produce in production.

This loader exists to enable local development without a running metadata API.
"""

import json
import logging

from dritimeseriesprocessor import PACKAGE_ROOT
from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.eddypro.eddypro_config_builder import EddyProSiteConfig
from dritimeseriesprocessor.utils.enums import ConfigurationType, ProcessingLevel

logger = logging.getLogger(__name__)


class FluxMetadataLoader:
    """Loads EddyPro metadata from local JSON fixtures for local development.

    In production, this data comes from the FDRI Metadata API via the DAG builder.
    This loader produces the same domain model objects, enabling local development
    without a running metadata API.
    """

    METADATA_DIR = PACKAGE_ROOT / "__metadata__" / "eddypro"

    def __init__(self, network: str, sites: list[str]) -> None:
        self._network = network
        self._sites = sites

    def load_site_metadata(self) -> dict[str, SiteMetadata]:
        """Load site metadata from sites.json.

        Returns:
            Dict keyed by site_id URI (e.g. "http://fdri.ceh.ac.uk/id/site/flux-plynl").
        """
        data = self._load_json("sites.json")
        result: dict[str, SiteMetadata] = {}

        for site_key in self._sites:
            if site_key not in data:
                raise KeyError(f"Site {site_key!r} not found in sites.json. Available: {list(data.keys())}")

            site_data = data[site_key]
            metadata = SiteMetadata(
                site_id=site_data["site_id"],
                network=site_data["network"],
                alt_id=site_data.get("alt_id"),
                full_name=site_data.get("full_name"),
                lat=site_data.get("lat"),
                lon=site_data.get("lon"),
                altitude=site_data.get("altitude"),
                easting=site_data.get("easting"),
                northing=site_data.get("northing"),
            )
            result[metadata.site_id] = metadata

        logger.info("Loaded site metadata for %d sites", len(result))
        return result

    def load_datasets(self) -> dict[str, TimeSeriesContainer]:
        """Load dataset definitions from datasets.json"""
        data = self._load_json("datasets.json")
        eddypro_cfg = self._load_json("eddypro_configs.json")
        containers: dict[str, TimeSeriesContainer] = {}

        for site_key in self._sites:
            if site_key not in data:
                raise KeyError(f"Site {site_key!r} not found in datasets.json. Available: {list(data.keys())}")

            site_data = data[site_key]
            raw_container = self._build_container(site_data["raw"])
            processed_container = self._build_container(site_data["processed"])

            site_eddypro = eddypro_cfg.get(site_key, {})
            params = {"dep_ts": raw_container.ts_id}
            for key in (
                "file_prototype",
                "master_sonic",
                "acquisition_frequency",
                "file_duration",
                "avrg_len",
                "sw_version",
            ):
                if key in site_eddypro:
                    params[key] = site_eddypro[key]

            # Wire up the dependency: processed depends on raw via eddypro config
            eddypro_config = DataProcessingConfig(
                ts_id=processed_container.ts_id,
                config_id=f"local-eddypro-{site_key}",
                config_type=ConfigurationType.EDDYPRO,
                method_configs=[
                    DataProcessingMethodConfig(
                        method="eddypro",
                        params=params,
                    )
                ],
            )
            processed_container.attach_configs([eddypro_config])

            containers[raw_container.ts_id] = raw_container
            containers[processed_container.ts_id] = processed_container

        logger.info("Loaded %d dataset containers", len(containers))
        return containers

    def load_eddypro_site_configs(self) -> dict[str, EddyProSiteConfig]:
        """Load EddyPro-specific site configs from eddypro_configs.json.

        Returns:
            Dict keyed by site identifier (e.g. "PLYNL").
        """
        data = self._load_json("eddypro_configs.json")
        configs: dict[str, EddyProSiteConfig] = {}

        for site_key in self._sites:
            if site_key not in data:
                raise KeyError(f"Site {site_key!r} not found in eddypro_configs.json. Available: {list(data.keys())}")

            site_data = data[site_key]
            configs[site_key] = EddyProSiteConfig(
                site_id=site_data["site_id"],
                latitude=site_data["latitude"],
                longitude=site_data["longitude"],
                altitude=site_data["altitude"],
                file_prototype=site_data["file_prototype"],
            )

        logger.info("Loaded EddyPro site configs for %d sites", len(configs))
        return configs

    def _build_container(self, definition: dict) -> TimeSeriesContainer:
        """Build a TimeSeriesContainer from a dataset definition dict.

        Args:
            definition: A dataset definition from datasets.json.

        Returns:
            A populated TimeSeriesContainer.
        """
        return TimeSeriesContainer(
            ts_id=definition["ts_id"],
            network=definition["network"],
            source_bucket=definition["source_bucket"],
            source_dataset=definition["source_dataset"],
            source_column=definition["source_column"],
            source_site=definition["source_site"],
            source_site_identifier=definition["source_site_identifier"],
            time_column_name=definition["time_column_name"],
            resolution=definition["resolution"],
            periodicity=definition["periodicity"],
            processing_level=ProcessingLevel(definition["processing_level"]),
        )

    @classmethod
    def _load_json(cls, filename: str) -> dict:
        """Load a JSON file from the eddypro metadata directory.

        Args:
            filename: Name of the JSON file to load.

        Returns:
            Parsed JSON data.
        """
        path = cls.METADATA_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Metadata fixture not found: {path}")
        return json.loads(path.read_text())

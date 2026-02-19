"""EddyPro processing pipeline.

This module defines the :class:`~dritimeseriesprocessor.processing.eddypro_processor.EddyProProcessor`,
which orchestrates file-based flux data processing via the EddyPro binary.

It is intentionally separate from :class:`~dritimeseriesprocessor.processing.time_series_processor.TimeSeriesProcessor`
because the processing model is fundamentally different:

- TimeSeriesProcessor: column-at-a-time, in-memory TimeFrame, correction/QC/infill chain
- EddyProProcessor: whole-site, file-based, external binary, output is a directory of files

Like the time-series pipeline, EddyPro processing is driven by a
:class:`~dritimeseriesprocessor.dag.dataset_dependency_graph.DatasetDependencyGraph`.
"""

import logging
import tempfile
from datetime import date
from pathlib import Path

from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.eddypro.eddypro_config_builder import EddyProConfigBuilder, EddyProSiteConfig
from dritimeseriesprocessor.operations.eddypro.eddypro_pipeline import EddyProPipeline
from dritimeseriesprocessor.operations.eddypro.eddypro_runner import EddyProRunner
from dritimeseriesprocessor.routers.data.flux_data_router import FluxDataRouter
from dritimeseriesprocessor.utils.enums import MethodType

logger = logging.getLogger(__name__)


class EddyProProcessor:
    """Orchestrates EddyPro processing for flux datasets.

    Analogous to TimeSeriesProcessor but for file-based EddyPro processing.

    Processes datasets in dependency order using a DatasetDependencyGraph, running EddyPro
    for containers whose method_type is EDDYPRO.
    """

    def __init__(
        self,
        graph: DatasetDependencyGraph,
        flux_data_router: FluxDataRouter,
        project_template: Path,
        metadata_template: Path,
        start_date: date,
        end_date: date,
    ) -> None:
        """Initialise the EddyPro processor.

        Args:
            graph: Dependency graph containing resolved dataset containers.
            flux_data_router: Router for downloading/uploading flux files from/to S3.
            project_template: Path to the .eddypro template file.
            metadata_template: Path to the .metadata template file.
            start_date: Start of the processing window.
            end_date: End of the processing window.
        """
        self.graph = graph
        self._flux_data_router = flux_data_router
        self._project_template = project_template
        self._metadata_template = metadata_template
        self._start_date = start_date
        self._end_date = end_date
        self._site_metadata_by_alt_id = self._index_site_metadata(graph.site_metadata)

    def run(self) -> None:
        """Execute the EddyPro processing pipeline for all EDDYPRO-type datasets."""
        if not self.graph.datasets:
            logger.warning("No datasets found in dependency graph.")
            return

        layers = self.graph.layered_topo_sort()
        eddypro_dataset_ids: list[str] = []
        for layer in layers:
            for dataset_id in layer:
                if self.graph.datasets[dataset_id].method_type() == MethodType.EDDYPRO:
                    eddypro_dataset_ids.append(dataset_id)

        if not eddypro_dataset_ids:
            logger.warning("No EddyPro datasets found in dependency graph.")
            return

        logger.info(
            "EddyPro processing started (datasets=%d, layers=%d).",
            len(eddypro_dataset_ids),
            len(layers),
        )

        succeeded = 0
        failed = 0
        for layer in layers:
            for dataset_id in layer:
                container = self.graph.datasets[dataset_id]
                if container.method_type() != MethodType.EDDYPRO:
                    continue

                try:
                    self._process_site(container)
                except Exception:
                    failed += 1
                    logger.exception("EddyPro processing failed for: %s", container.ts_id)
                else:
                    succeeded += 1

        logger.info("EddyPro processing finished (succeeded=%d, failed=%d).", succeeded, failed)

    def _process_site(self, container: TimeSeriesContainer) -> None:
        """Process a single flux site through EddyPro.

        Args:
            container: The processed dataset container (method_type == EDDYPRO).
        """
        site_id = container.source_site_identifier
        logger.info("Processing site: %s (dataset: %s)", site_id, container.ts_id)

        site_config = self._build_site_config(container)

        with tempfile.TemporaryDirectory(prefix=f"eddypro_{site_id}_") as tmpdir:
            working_dir = Path(tmpdir)
            raw_dir = working_dir / "raw_data"
            raw_dir.mkdir()

            # Download raw data files
            raw_dep = self._get_raw_dependency(container)
            self._flux_data_router.download_raw_files(
                bucket=raw_dep.source_bucket,
                network=raw_dep.network,
                dataset=raw_dep.source_dataset,
                site=site_id,
                start_date=self._start_date,
                end_date=self._end_date,
                local_dir=raw_dir,
            )

            # Download ancillary files (biomet, dynamic metadata)
            biomet_path = self._flux_data_router.download_biomet(
                bucket=raw_dep.source_bucket,
                network=raw_dep.network,
                site=site_id,
                local_dir=working_dir,
            )
            dyn_meta_path = self._flux_data_router.download_dynamic_metadata(
                bucket=raw_dep.source_bucket,
                network=raw_dep.network,
                site=site_id,
                local_dir=working_dir,
            )

            # Build config and run EddyPro
            config_builder = EddyProConfigBuilder(site_config)
            runner = EddyProRunner()
            pipeline = EddyProPipeline(
                runner=runner,
                config_builder=config_builder,
                project_template=self._project_template,
                metadata_template=self._metadata_template,
            )

            result = pipeline.run(
                raw_data_dir=raw_dir,
                working_dir=working_dir,
                start_date=self._start_date,
                end_date=self._end_date,
                biomet_file=biomet_path,
                dynamic_metadata_file=dyn_meta_path,
            )

            # Upload output directory to processed bucket
            run_date = self._start_date.strftime("%Y-%m-%d")
            uploaded = self._flux_data_router.upload_output_directory(
                bucket=container.source_bucket,
                local_output_dir=result.output_dir,
                network=container.network,
                dataset=container.source_dataset,
                site=site_id,
                run_date=run_date,
            )
            logger.info("Uploaded %d EddyPro output files for site %s", uploaded, site_id)

    def _build_site_config(self, container: TimeSeriesContainer) -> EddyProSiteConfig:
        """Build the EddyPro site config for this dataset from site metadata + processing config params.

        In production, the EDDYPRO processing configuration is expected to include parameters like
        ``file_prototype`` and ``master_sonic``. Site latitude/longitude/altitude come from the
        site metadata endpoint.
        """
        site_id = container.source_site_identifier
        site_meta = self._site_metadata_by_alt_id.get(site_id)
        if not site_meta:
            raise KeyError(
                f"No site metadata found for {site_id!r}. Available: {sorted(self._site_metadata_by_alt_id)}"
            )

        file_prototype = self._get_method_param(container, "file_prototype")

        if site_meta.lat is None or site_meta.lon is None or site_meta.altitude is None:
            raise ValueError(
                "Site metadata missing required fields (lat/lon/altitude) "
                f"for {site_id!r}: lat={site_meta.lat}, lon={site_meta.lon}, altitude={site_meta.altitude}"
            )

        return EddyProSiteConfig(
            site_id=site_id,
            latitude=site_meta.lat,
            longitude=site_meta.lon,
            altitude=site_meta.altitude,
            canopy_height=site_meta.canopy_height,
            displacement_height=site_meta.displacement_height,
            roughness_length=site_meta.roughness_length,
            file_prototype=file_prototype,
        )

    def _get_raw_dependency(self, container: TimeSeriesContainer) -> TimeSeriesContainer:
        """Resolve the raw dependency container for an EddyPro processed dataset."""
        dep_ids = container.all_dependencies()
        if not dep_ids:
            raise ValueError(f"EddyPro dataset has no raw dependency: {container.ts_id}")

        raw_id = dep_ids[0]
        if raw_id not in self.graph.datasets:
            raise KeyError(f"Raw dependency {raw_id!r} not found in graph for {container.ts_id}")

        return self.graph.datasets[raw_id]

    @staticmethod
    def _index_site_metadata(site_metadata: dict[str, SiteMetadata]) -> dict[str, SiteMetadata]:
        """Index site metadata by site alt_id for quick lookup."""
        indexed: dict[str, SiteMetadata] = {}
        for meta in site_metadata.values():
            if meta.alt_id:
                indexed[meta.alt_id] = meta
        return indexed

    @staticmethod
    def _get_method_param(container: TimeSeriesContainer, key: str) -> str:
        if not container.method_config:
            raise ValueError(f"Dataset has no method_config attached: {container.ts_id}")
        if not container.method_config.method_configs:
            raise ValueError(f"Dataset method_config has no method_configs: {container.ts_id}")

        params = container.method_config.method_configs[0].params
        if key not in params:
            raise KeyError(f"Missing required EddyPro parameter {key!r} for dataset: {container.ts_id}")

        value = params[key]
        if not isinstance(value, str) or not value:
            raise ValueError(f"Invalid EddyPro parameter {key!r} for dataset {container.ts_id}: {value!r}")
        return value

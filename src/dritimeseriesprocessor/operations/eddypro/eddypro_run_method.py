"""The EddyProRun derivation method, which runs the EddyPro flux processing pipeline.

Kept out of `derivation_methods.py` because it pulls in the service's EddyPro/S3 I/O stack
(`EddyProPipeline`, `EddyProRunner`, `DataRouter`), which the pure calculation-based derivation
methods do not need.
"""

import logging
from dataclasses import replace
from datetime import date, datetime, timedelta

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.derivation.derivation_methods import DerivationMethod
from dritimeseriesprocessor.operations.eddypro.eddypro_pipeline import EddyProPipeline
from dritimeseriesprocessor.operations.eddypro.eddypro_runner import EddyProRunner
from dritimeseriesprocessor.operations.eddypro.flux_despike import despike_df
from dritimeseriesprocessor.routers.data.data_router import DataRouter
from dritimeseriesprocessor.utils.enums import ProcessingLevel

logger = logging.getLogger(__name__)


@DerivationMethod.register
class EddyProRun(DerivationMethod):
    """Run the EddyPro flux processing pipeline to produce an ObservationDataset bundle.

    Reads all required context from `config.params`, which is populated by the processor
    (`start_date`, `end_date`, `site_metadata`) and the derivation pipeline
    (`container`, `dataset_repository`). The raw .dat input is staged locally during the
    LOAD step, with its directory recorded on the raw dependency's `staged_dir`.
    """

    name = "eddypro-run"

    # Should these be wired through the processing config / metadata API?
    # In practice these parameters are unlikely to change
    # H and Tau are the only flux variables that require MAD despiking,
    # R_SW_in_Avg is the standard day/night discriminator,
    # and the sensitivity/window values are established defaults from the legacy processing script.
    _DESPIKE_COLUMNS = ["H", "Tau"]
    _DESPIKE_REFERENCE_COLUMN = "R_SW_in_Avg"
    _DESPIKE_WINDOW_DAYS = 13
    _DESPIKE_LOOKBACK_DAYS = 13
    _DESPIKE_SENSITIVITY = 5.5
    _DESPIKE_ITERATIONS = 1

    def run(self, tf: ts.TimeFrame | None, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        container = config.params["container"]
        dataset_repository = config.params["dataset_repository"]
        start_date = config.params["processing_start_date"]
        end_date = config.params["processing_end_date"]
        site_metadata = config.params["site_metadata"]

        if len(container.base_dependency) != 1:
            raise ValueError(f"Expected exactly one base dependency. Got: {container.base_dependency}")
        raw_container = dataset_repository[container.base_dependency[0]]

        if raw_container.staged_dir is None:
            raise ValueError(f"Raw dependency {raw_container.ts_id} was not staged locally before the EddyPro run.")

        ancillary_containers = [
            dataset_repository[ds_id] for ds_id in container.all_dependencies() if ds_id != raw_container.ts_id
        ]

        df = EddyProPipeline(runner=EddyProRunner()).run(
            raw_data_dir=raw_container.staged_dir,
            method_config=config,
            site_metadata=site_metadata,
            start_date=start_date,
            end_date=end_date,
            ancillary_containers=ancillary_containers,
        )
        resolution = f"PT{config.params['file_duration']}M"
        data_router = config.params.get("data_router")
        if data_router is not None:
            # ObservationDataset bundles have source_bucket=None; find it from a sibling
            # processed dataset that does carry the bucket in the repository.
            processed_container = next(
                (
                    c
                    for c in dataset_repository.values()
                    if c.source_bucket is not None and c.processing_level is ProcessingLevel.PROCESSED
                ),
                None,
            )
            df = self._run_despiking(df, container, start_date, resolution, data_router, processed_container)
        else:
            logger.warning("data_router not available in EddyProRun params; despiking skipped.")

        container.time_column_name = "time"
        container.resolution = resolution
        container.periodicity = container.resolution
        container.init_timeframe(df)
        return container.data

    @staticmethod
    def _run_despiking(
        df: pl.DataFrame,
        container: TimeSeriesContainer,
        start_date: date,
        resolution: str,
        data_router: DataRouter,
        processed_container: TimeSeriesContainer | None = None,
    ) -> pl.DataFrame:
        """Load prior history and apply MAD despiking to H and Tau in the EddyPro output.

        Args:
            df: EddyPro output DataFrame for the current processing window.
            container: The EddyPro bundle container (provides site identifier).
            start_date: Start of the current processing window (used to calculate lookback range).
            resolution: ISO-8601 resolution string (e.g. "PT30M") for the hive partition path.
            data_router: Router used to load historical processed data from S3.
            processed_container: A sibling processed container providing network and source_bucket.
                ObservationDataset bundles carry network=None and source_bucket=None, so the
                caller resolves both from a sibling dataset.
        """
        site = container.source_site_identifier
        # ObservationDataset bundles don't carry network or source_bucket.
        # Borrow both from a sibling processed container - same source _build_save_tasks uses.
        network = processed_container.network if processed_container is not None else None
        source_bucket = processed_container.source_bucket if processed_container is not None else None

        history_start = datetime.combine(
            start_date - timedelta(days=EddyProRun._DESPIKE_LOOKBACK_DAYS), datetime.min.time()
        )
        history_end = datetime.combine(start_date - timedelta(days=1), datetime.min.time())

        # Derive a per-column container from the bundle so query_by_date_range can build the
        # hive path. processing_level=PROCESSED signals the resolution-keyed path.
        history_columns = [*EddyProRun._DESPIKE_COLUMNS, EddyProRun._DESPIKE_REFERENCE_COLUMN]
        history_containers = [
            replace(
                container,
                network=network,
                source_bucket=source_bucket,
                source_site_identifier=site,
                resolution=resolution,
                time_column_name="time",
                source_column=col,
                processing_level=ProcessingLevel.PROCESSED,
            )
            for col in history_columns
        ]

        try:
            history_df = data_router.query_by_date_range(
                *history_containers, start_date=history_start, end_date=history_end
            )
        except Exception:
            logger.warning(
                "Despiking skipped: failed to load history for site %s (window: %s to %s).",
                site,
                history_start,
                history_end,
            )
            return df

        if history_df is None or history_df.is_empty():
            logger.warning(
                "Despiking skipped: no history data available for site %s (window: %s to %s).",
                site,
                history_start,
                history_end,
            )
            return df

        return despike_df(
            current_df=df,
            history_df=history_df,
            columns=EddyProRun._DESPIKE_COLUMNS,
            reference_column=EddyProRun._DESPIKE_REFERENCE_COLUMN,
            window_days=EddyProRun._DESPIKE_WINDOW_DAYS,
            sensitivity=EddyProRun._DESPIKE_SENSITIVITY,
            iterations=EddyProRun._DESPIKE_ITERATIONS,
            output_names={"H": "H_despiked", "Tau": "Tau_L2"},
        )

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        raise NotImplementedError("EddyProRun overrides run() directly")

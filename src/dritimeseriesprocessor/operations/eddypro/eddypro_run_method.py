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
from dritimeseriesprocessor.utils.enums import DatasetType, ProcessingLevel

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

    def run(self, config: DataProcessingMethodConfig) -> ts.TimeFrame:
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
            # The bundle's own access URL is not where the despiking history is saved; find it from a sibling
            # processed timeseries dataset in the repository.
            access_url = next(
                (
                    c.access_url
                    for c in dataset_repository.values()
                    if c.access_url is not None
                    and c.processing_level is ProcessingLevel.PROCESSED
                    and c.dataset_type is DatasetType.TIMESERIES_DATASET
                ),
                None,
            )
            df = self._run_despiking(df, container, start_date, data_router, access_url)
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
        data_router: DataRouter,
        processed_access_url: str | None,
    ) -> pl.DataFrame:
        """Load prior history and apply MAD despiking to H and Tau in the EddyPro output.

        Args:
            df: EddyPro output DataFrame for the current processing window.
            container: The EddyPro bundle container (provides site identifier).
            start_date: Start of the current processing window (used to calculate lookback range).
            data_router: Router used to load historical processed data from storage.
            processed_access_url: Access URL of the processed collection that holds the history, or None if there isn't
                one.
        """
        site = container.source_site_identifier
        if processed_access_url is None:
            logger.warning("Despiking skipped: no processed timeseries dataset to read history from for site %s.", site)
            return df

        history_start = datetime.combine(
            start_date - timedelta(days=EddyProRun._DESPIKE_LOOKBACK_DAYS), datetime.min.time()
        )
        history_end = datetime.combine(start_date - timedelta(days=1), datetime.min.time())

        # One container per history column, all read from the sibling's access URL
        history_columns = [*EddyProRun._DESPIKE_COLUMNS, EddyProRun._DESPIKE_REFERENCE_COLUMN]
        history_containers = [
            replace(container, access_url=processed_access_url, time_column_name="time", source_column=column)
            for column in history_columns
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

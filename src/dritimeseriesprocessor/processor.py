import logging
from datetime import datetime
from typing import Dict, Union

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.infilling.infiller import run_infilling
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.preprocessing.preprocessor import run_preprocess
from dritimeseriesprocessor.quality_control.quality_controller import run_quality_control
from dritimeseriesprocessor.s3_crud import data_manager

logger = logging.getLogger(__name__)


def load_data(ts_metadata: Dict[str, Dict[str, str]], start_date: datetime, end_date: datetime) -> pl.DataFrame:
    """
    Load in data for the given timeseries from S3 using the data_manager.

    Args:
        ts_metadata: Metadata for timeseries ID to load
        start_date: The start date of the data
        end_date: The end date of the data

    Returns:
        pl.DataFrame: A Polars DataFrame containing the loaded data.
    """
    logger.info(
        {
            "dataset": ts_metadata["sourceDataset"],
            "bucket": ts_metadata["sourceBucket"],
            "column": ts_metadata["sourceColumnName"],
            "site": ts_metadata["sourceSite"],
            "start_date": start_date,
            "end_date": end_date,
        }
    )

    bucket_data = data_manager.query_by_date_range(
        bucket_name=ts_metadata["sourceBucket"],
        prefix=f"cosmos/dataset={ts_metadata['sourceDataset']}",
        start_date=start_date,
        end_date=end_date,
        site_ids=[ts_metadata["sourceSite"]],
        columns=[ts_metadata["sourceColumnName"]],
    )

    if bucket_data.shape[0] == 0:
        metrics.record_no_data_run()
        logger.info("No data returned from the query.")
        metrics.export_metrics_to_pushgateway(
            url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
        )
        return None

    return TimeSeries(
        bucket_data,
        "time",
        ts_metadata["resolution"],
        ts_metadata["periodicity"],
        metadata={
            "site_id": ts_metadata["sourceSite"],
            "column_name": ts_metadata["sourceColumnName"],
            "processing_level": ts_metadata["processing_level"],
        },
    )


def process_timeseries(
    ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]],
) -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
    """
    Process the timeseries data.

    Args:
        ts_ids: Metadata and data for timeseries ids

    Returns:
        ts_ids: Metadata and processed data for timeseries ids
    """
    # Correction
    ts_ids = run_preprocess(ts_ids)

    # Quality control
    ts_ids = run_quality_control(ts_ids, remove=True)

    # Infilling
    ts_ids = run_infilling(ts_ids)

    return ts_ids

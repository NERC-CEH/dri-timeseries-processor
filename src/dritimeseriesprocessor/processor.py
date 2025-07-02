import logging
import os
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

    ts = TimeSeries(
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

    # To help test the processor with large amounts of data, we bypass any errors
    # raised by duplicate timestamps when running locally. In production we want
    # the default behaviour which is too raise the error.
    if "environment" not in os.environ:
        ts.on_duplicates = "keep_first"

    return ts


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
    # Subset entries with a "data" key
    ts_ids_with_data = {k: v for k, v in ts_ids.items() if "data" in v}
    ts_ids_with_no_data = {k: v for k, v in ts_ids.items() if "data" not in v}

    # Correction
    ts_ids_with_data = run_preprocess(ts_ids_with_data)

    # Quality control
    ts_ids_with_data = run_quality_control(ts_ids_with_data, remove=True)

    # Infilling
    ts_ids_with_data = run_infilling(ts_ids_with_data)

    return ts_ids_with_data | ts_ids_with_no_data

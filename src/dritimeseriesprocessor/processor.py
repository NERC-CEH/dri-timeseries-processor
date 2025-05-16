import logging
from datetime import datetime
from typing import Dict, List, Union

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.flagging.flagger import (
    add_initial_core_flags,
    update_infill_core_flags,
    update_preprocess_core_flags,
    update_quality_control_core_flags,
)
from dritimeseriesprocessor.infilling.infiller import run_infilling
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.preprocessing.preprocessor import run_preprocess
from dritimeseriesprocessor.quality_control.quality_controller import run_quality_control
from dritimeseriesprocessor.s3_crud import data_manager

logger = logging.getLogger(__name__)


def load_data_for_group(
    ts_metadata: Dict[str, Dict[str, str]], site_id: str, start_date: datetime, end_date: datetime
) -> pl.DataFrame:
    """
    Load in data for the given timeseries IDs.

    This function has three steps:
    1. Prepare the data to load by grouping the timeseries IDs by their dataset and bucket.
    2. Load the data from S3 using the data_manager.
    3. Merge the loaded data together into a single Polars DataFrame.

    The "group" is timeseries IDs that are of the same periodicity. This is so the data can be merged together.

    Args:
        ts_metadata: Metadata for timeseries IDs to load
        site_id: The site ID for the timeseries group.
        start_date: The start date of the data
        end_date: The end date of the data

    Returns:
        pl.DataFrame: A Polars DataFrame containing the loaded data.
    """
    data_to_load = prepare_data_to_load(ts_metadata)

    dfs = []
    for dataset, buckets in data_to_load.items():
        for bucket_name, columns in buckets.items():
            logger.info(
                f"Loading data. Dataset:{dataset}. Bucket:{bucket_name}. Columns:{columns} "
                f"Site:{site_id}. Dates:{start_date} to {end_date}"
            )
            bucket_data = data_manager.query_by_date_range(
                bucket_name=bucket_name,
                prefix=f"cosmos/dataset={dataset}",
                start_date=start_date,
                end_date=end_date,
                site_ids=[site_id],
                columns=columns,
            )

            if bucket_data.shape[0] == 0:
                metrics.record_no_data_run()
                logger.info("No data returned from the query.")
                metrics.export_metrics_to_pushgateway(
                    url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
                )
            else:
                bucket_data = add_processing_dependencies(bucket_data)
                dfs.append(bucket_data)

    return merge_data(dfs)


def merge_data(dfs: List[pl.DataFrame]) -> Union[None, pl.DataFrame]:
    """
    Merge dataframes together (if they exist).

    Args:
        dfs: List of Polars DataFrames to merge.

    Returns:
        pl.DataFrame: The merged Polars DataFrame, or None if no dataframes are provided.
    """
    # Filter out empty dataframes (so that concat doesn't fail)
    dfs = [df for df in dfs if df.height > 0]

    if len(dfs) == 0:
        return None
    else:
        return pl.concat(dfs, how="align")


def prepare_data_to_load(ts_metadata: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, set]]:
    """
    Format the timeseries ID metadata so it can be loaded.

    Loop through the metadata for the timeseries IDs to load and group together column
    names that live in the same dataset and bucket. This structured dictionary can then
    be used to load data from S3.

    Args:
        ts_metadata: Metadata for timeseries IDs to load

    Returns:
        dict: A nested dictionary structure for datasets, buckets, and columns to load.
    """
    data_to_load = {}
    for ts_item in ts_metadata.values():
        dataset = ts_item["sourceDataset"]
        bucket_name = ts_item["sourceBucket"]
        column_name = ts_item["sourceColumnName"]

        if dataset not in data_to_load:
            data_to_load[dataset] = {}

        if bucket_name not in data_to_load[dataset]:
            data_to_load[dataset][bucket_name] = set()

        data_to_load[dataset][bucket_name].add(column_name)

    return data_to_load


def add_processing_dependencies(bucket_data: pl.DataFrame) -> pl.DataFrame:
    """
    TODO
    Placeholder function to add processing dependencies to the data.
    This function is acurrently hard coded to add  BATTV and SCANS columns.

    Args:
        bucket_data: The Polars DataFrame containing the bucket data.

    Returns:
        pl.DataFrame: The Polars DataFrame with dummy data added.
    """
    bucket_data = bucket_data.with_columns(
        [
            pl.Series([12 for _ in range(len(bucket_data))]).alias("BATTV"),
            pl.Series(range(len(bucket_data))).alias("SCANS"),
        ]
    )
    logger.info(f"Added dummy data, shape: {bucket_data.shape}")
    return bucket_data


def process_timeseries(ts: TimeSeries, ts_metadata: Dict[str, Dict[str, str]]) -> TimeSeries:
    """
    Process the timeseries data.

    Args:
        ts: The timeseries object to process.
        ts_metadata: Metadata for timeseries IDs to process.

    Returns:
        TimeSeries: The processed timeseries object.
    """
    # Initalise core flag system
    ts = add_initial_core_flags(ts)

    # Correction
    ts = run_preprocess(ts)
    ts = update_preprocess_core_flags(ts)
    logger.info(f"Ran preprocessor successfully, shape: {ts.df.shape}")

    # Quality control
    ts = run_quality_control(ts, ts_metadata, remove=True)
    ts = update_quality_control_core_flags(ts)
    qcflag_columns = [col for col in ts.columns if col.endswith("_QCFLAG")]
    flags_count = len(qcflag_columns)
    logger.info(f"Number of QC flag columns: {flags_count}")
    metrics.increment_flags(flags_count)

    with pl.Config(tbl_rows=100):
        logger.info(ts.df.limit(100))

    # Infilling
    ts = run_infilling(ts, ts_metadata)
    ts = update_infill_core_flags(ts)

    with pl.Config(tbl_rows=100):
        logger.info(ts.df.limit(100))

    return ts

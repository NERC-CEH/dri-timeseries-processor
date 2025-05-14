import logging
from datetime import datetime

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


# Setup metrics
# -------------
metrics.setup_metrics()


def load_data_for_group(ts_metadata: dict, site_id: str, start_date: datetime, end_date: datetime) -> pl.DataFrame:
    """
    Load data for given timeseries IDs. The "group" is timeseries IDs that are of the same
    periodicity. This is so the data can be merged together.

    Args:
        ts_metadata: Metadata for timeseries IDs to load
        site_id: The site ID for the timeseries group.
        start_date: The start date of the data
        end_date: The end date of the data

    Returns:
        pl.DataFrame: A Polars DataFrame containing the loaded data.
    """
    data_to_load = prepare_data_to_load(ts_metadata)

    data = None
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
                data = merge_data(data, bucket_data)

    return data


def prepare_data_to_load(ts_metadata: dict) -> dict:
    """
    Prepare the data structure for loading timeseries data.

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


def merge_data(existing_data: pl.DataFrame, new_data: pl.DataFrame) -> pl.DataFrame:
    """
    Merge new data into the existing data.

    Args:
        existing_data: The existing Polars DataFrame.
        new_data: The new Polars DataFrame to merge.

    Returns:
        pl.DataFrame: The merged Polars DataFrame.
    """
    if existing_data is None:
        return new_data

    if new_data.height == 0:
        logger.info("No new data to merge.")
        return existing_data

    # Check what expected height of the data should be after merge
    expected_height = max(existing_data.height, new_data.height)

    matching_columns = set(existing_data.columns) & set(new_data.columns)

    existing_data = existing_data.join(new_data, on=matching_columns, how="full", coalesce=True)

    if existing_data.height != expected_height:
        msg = f"Data merge failed. Extra rows added: {existing_data}"
        logger.error(msg)
        raise ValueError(msg)

    return existing_data


def process_timeseries(ts: TimeSeries, ts_metadata: dict[str, dict]) -> TimeSeries:
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

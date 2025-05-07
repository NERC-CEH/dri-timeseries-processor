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
from dritimeseriesprocessor.logger import setup_logging
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.preprocessing.preprocessor import run_preprocess
from dritimeseriesprocessor.quality_control.quality_controller import run_quality_control
from dritimeseriesprocessor.s3_crud import data_manager

logger = logging.getLogger(__name__)
setup_logging()


def load_data_for_group(
    ts_group: dict, all_timeseries_ids_metadata: dict, start_date: datetime, end_date: datetime
) -> pl.DataFrame:
    """
    Load data for a group of timeseries IDs.

    Args:
        ts_group: A dictionary containing information about the timeseries group,
            including timeseries IDs, site ID, resolution, and periodicity.
        all_timeseries_ids_metadata: Metadata for all timeseries IDs, mapping timeseries IDs
            to their respective metadata.
        start_date: The start date of the data
        end_date: The end date of the data

    Returns:
        pl.DataFrame: A Polars DataFrame containing the loaded data for the specified group.
    """
    data_to_load = {}
    for ts_id in ts_group["timeseries_ids"]:
        ts_metadata = all_timeseries_ids_metadata[ts_id]
        dataset = ts_metadata["sourceDataset"]
        bucket_name = ts_metadata["sourceBucket"]
        column_name = ts_metadata["sourceColumnName"]

        if dataset not in data_to_load:
            data_to_load[dataset] = {}
        if bucket_name not in data_to_load[dataset]:
            data_to_load[dataset][bucket_name] = {"columns": set()}
        data_to_load[dataset][bucket_name]["columns"].add(column_name)

    data = None
    for dataset, buckets in data_to_load.items():
        for bucket_name, params in buckets.items():
            logger.info(
                f"Processing {dataset} with columns {params['columns']} for site {ts_group['site_id']} "
                f"between {start_date} and {end_date}"
            )
            bucket_data = data_manager.query_by_date_range(
                bucket_name=bucket_name,
                prefix=f"cosmos/dataset={dataset}",
                start_date=start_date,
                end_date=end_date,
                site_ids=[ts_group["site_id"]],
                columns=params["columns"],
            )

            if bucket_data.shape[0] == 0:
                metrics.record_no_data_run()
                logger.info("No data returned from the query.")
                metrics.export_metrics_to_pushgateway(
                    url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
                )
            else:
                logger.info(f"Retrieved data from s3: {bucket_data.shape}")
                bucket_data = bucket_data.with_columns(
                    [
                        pl.Series([12 for i in range(len(bucket_data))]).alias("BATTV"),
                        pl.Series(i for i in range(len(bucket_data))).alias("SCANS"),
                    ]
                )
                logger.info(f"Added dummy data, shape: {bucket_data.shape}")
                if data is None:
                    data = bucket_data
                else:
                    matching_columns = set(data.columns) & set(bucket_data.columns)
                    data = data.join(bucket_data, left_on=matching_columns, right_on=matching_columns, how="left")
    return data


def process_timeseries(ts: TimeSeries, ts_ids: list[str], all_timeseries_ids_metadata: dict[str, dict]) -> TimeSeries:
    """
    Process the timeseries data.

    Args:
        ts: The timeseries object to process.
        ts_ids: List of timeseries IDs to process.
        all_timeseries_ids_metadata: Metadata for all timeseries IDs.

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
    ts = run_quality_control(ts, ts_ids, all_timeseries_ids_metadata, remove=True)
    ts = update_quality_control_core_flags(ts)
    qcflag_columns = [col for col in ts.columns if col.endswith("_QCFLAG")]
    flags_count = len(qcflag_columns)
    logger.info(f"Number of QC flag columns: {flags_count}")
    metrics.increment_flags(flags_count)

    with pl.Config(tbl_rows=100):
        logger.info(ts.df.limit(100))

    # Infilling
    ts = run_infilling(ts, ts_ids, all_timeseries_ids_metadata)
    ts = update_infill_core_flags(ts)

    with pl.Config(tbl_rows=100):
        logger.info(ts.df.limit(100))

    return ts

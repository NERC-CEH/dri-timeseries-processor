import logging
import os
from datetime import datetime
from typing import Dict

from time_stream import TimeSeries

from dritimeseriesprocessor.correcting.correcter import run_corrections
from dritimeseriesprocessor.infilling.infiller import run_infilling
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.quality_control.quality_controller import run_quality_control
from dritimeseriesprocessor.s3_crud import data_manager
from dritimeseriesprocessor.timeseries_container import TimeseriesContainer

logger = logging.getLogger(__name__)


def load_data(ts_container: TimeseriesContainer, start_date: datetime, end_date: datetime) -> TimeSeries:
    """
    Load in data for the given timeseries from S3 using the data_manager.

    Args:
        ts_container: Container for timeseries data to load
        start_date: The start date of the data
        end_date: The end date of the data

    Returns:
        TimeSeries: A timeseries instance containing the loaded data.
    """
    logger.info(
        {
            "dataset": ts_container.sourceDataset,
            "bucket": ts_container.sourceBucket,
            "column": ts_container.sourceColumnName,
            "site": ts_container.sourceSite,
            "start_date": start_date,
            "end_date": end_date,
        }
    )

    bucket_data = data_manager.query_by_date_range(
        bucket_name=ts_container.sourceBucket,
        prefix=f"cosmos/dataset={ts_container.sourceDataset}",
        start_date=start_date,
        end_date=end_date,
        site_ids=[ts_container.sourceSite],
        columns=[ts_container.sourceColumnName],
    )

    if bucket_data.shape[0] == 0:
        metrics.record_no_data()
        logger.warning("No data returned from the query.")
        metrics.export_metrics_to_pushgateway(
            url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
        )

    ts = TimeSeries(
        bucket_data,
        "time",
        ts_container.resolution,
        ts_container.periodicity,
        metadata={
            "site_id": ts_container.sourceSite,
            "column_name": ts_container.sourceColumnName,
            "processing_level": ts_container.processing_level,
        },
    )

    # To help test the processor with large amounts of data, we bypass any errors
    # raised by duplicate timestamps when running locally. In production we want
    # the default behaviour which is too raise the error.
    if "environment" not in os.environ:
        ts.on_duplicates = "keep_first"

    return ts


def shift_processed_data(
    ts_ids: Dict[str, TimeseriesContainer],
) -> Dict[str, TimeseriesContainer]:
    """Move the processed data within raw timeseries ids to the processed timeseries ids

    Args:
        ts_ids: Metadata and data for timeseries ids

    Returns:
        A dictionary with the updated metadata.
    """
    for ts_id, ts_metadata in ts_ids.items():
        if ts_metadata.method_type == "process":
            # All processed timeseries IDs should have one input, the raw timeseries ID they are derived from.
            if len(ts_metadata.inputs) != 1:
                raise ValueError(f"Processed timeseries ID {ts_id} should have exactly one input.")

            raw_ts_id = ts_metadata.inputs[0]

            if ts_ids[raw_ts_id].data:
                # Move the data object from raw_ts_id to (processed) ts_id
                logger.info(f"Moving data from {raw_ts_id} to {ts_id}")
                ts_ids[ts_id].data = ts_ids[raw_ts_id].data
                ts_ids[raw_ts_id].data = None

    return ts_ids


def process_timeseries(
    ts_ids: Dict[str, TimeseriesContainer],
) -> Dict[str, TimeseriesContainer]:
    """
    Process the timeseries data.

    Args:
        ts_ids: Metadata and data for timeseries ids

    Returns:
        ts_ids: Metadata and processed data for timeseries ids
    """
    # Subset entries with a "data" key
    ts_ids_with_data = {ts_id: ts_container for ts_id, ts_container in ts_ids.items() if ts_container.data}
    ts_ids_with_no_data = {ts_id: ts_container for ts_id, ts_container in ts_ids.items() if not ts_container.data}

    # Corrections
    ts_ids_with_data = run_corrections(ts_ids_with_data)

    # Quality control
    ts_ids_with_data = run_quality_control(ts_ids_with_data, remove=True)

    # Infilling
    ts_ids_with_data = run_infilling(ts_ids_with_data)

    # Join back together
    ts_ids = ts_ids_with_data | ts_ids_with_no_data

    # Processed data is now in the ts_ids dict within the raw timeseries IDs.
    # Shift them to the processed timeseries IDs.
    ts_ids = shift_processed_data(ts_ids)

    return ts_ids

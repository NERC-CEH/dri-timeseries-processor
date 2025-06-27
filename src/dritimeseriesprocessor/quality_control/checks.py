import logging
from datetime import time
from typing import Dict, List, Union

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.quality_control.utils import (
    column_threshold_check,
)

logger = logging.getLogger(__name__)


def battery_voltage_check(
    ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]],
    ts_id: str,
    flag_column: str,
    flag_name: str,
    lt: float,
    dep_ts: str,
) -> TimeSeries:
    """Check that the battery voltage level is above the threshold.

    This function checks if the battery voltage ('BATTV' column) is below a certain threshold
    and applies a quality control flag to the specified column if it is.

    Args:
        ts_ids: Metadata and data for TimeSeries ids.
        ts_id: The ID of the TimeSeries to check.
        flag_column: The column to which flag value should be added.
        flag_name: The name of the flag to be added to the TimeSeries. This is the method name in the qc config.
        lt: The minimum value for the battery voltage.
        dep_ts: The name of the battv time series id to use for the battery voltage check.

    Returns:
        ts_ids: Metadata and data for TimeSeries with the quality control flag applied.
    """
    # Get data
    ts = ts_ids[ts_id]["data"]
    # Check if the dependent time series exists
    if dep_ts not in ts_ids:
        raise ValueError(f"Dependent Battery Voltage time series '{dep_ts}' not found in ts_ids.")
    battv_ts = ts_ids[dep_ts]["data"]

    # Perform check
    ts_ids[ts_id]["data"] = column_threshold_check(ts, battv_ts, flag_column, lt, "<", flag_name)

    return ts_ids


def range_check(
    ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]],
    ts_id: str,
    flag_column: str,
    flag_name: str,
    gt: float,
    lt: float,
) -> TimeSeries:
    """Check values falls between min and max range, applying a quality control flag if outside of range.

    Min and max range values are defined per site, per variable and per time resolution.

    Args:
        ts_ids: Metadata and data for TimeSeries ids.
        ts_id: The ID of the TimeSeries to check.
        flag_column: The column to which flag value should be added.
        flag_name: The name of the flag to be added to the TimeSeries. This is the method name in the qc config.
        gt: The minimum value for the range.
        lt: The maximum value for the range.

    Returns:
        ts_ids: Metadata and data for TimeSeries with the quality control flag applied.
    """
    # Get data
    ts = ts_ids[ts_id]["data"]

    # Apply range check
    expr = pl.col(ts.column_name).lt(lt) | pl.col(ts.column_name).gt(gt)
    ts.add_flag(flag_column, flag_name, expr)

    ts_ids[ts_id]["data"] = ts

    return ts_ids


def soilmet_scans_check(
    ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]],
    ts_id: str,
    flag_column: str,
    flag_name: str,
    lt: float,
    dep_ts: str,
) -> TimeSeries:
    """Check the soilmet scans value is above an acceptable threshold.

    Args:
        ts_ids: Metadata and data for TimeSeries ids.
        ts_id: The ID of the TimeSeries to check.
        flag_column: The column to which flag value should be added.
        flag_name: The name of the flag to be added to the TimeSeries. This is the method name in the qc config.
        lt: The minimum number of scans the check.
        dep_ts: The name of the scans timeseries ID to use for the scan check.

    Returns:
        ts_ids: Metadata and data for TimeSeries with the quality control flag applied.
    """
    # Get data
    ts = ts_ids[ts_id]["data"]
    # Get the dependent time series for scans
    if dep_ts not in ts_ids:
        raise ValueError(f"Dependent Scans time series '{dep_ts}' not found in ts_ids.")
    scans_ts = ts_ids[dep_ts]["data"]

    ts_ids[ts_id]["data"] = column_threshold_check(ts, scans_ts, flag_column, lt, "<", flag_name)

    return ts_ids


def error_codes_check(
    ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]], ts_id: str, flag_column: str, flag_name: str, value: List
) -> TimeSeries:
    """Add QC flag for expected error codes.

    Args:
        ts_ids: Metadata and data for TimeSeries ids.
        ts_id: The ID of the TimeSeries to check.
        flag_column: The column to which the flag value should be added.
        flag_name: The name of the flag to be added to the TimeSeries. This is the method name in the qc config.
        value: List of error codes to check for.

    Returns:
        ts_ids: Metadata and data for TimeSeries with the quality control flag applied.
    """
    # Get data
    ts = ts_ids[ts_id]["data"]

    for error_code in value:
        ts_ids[ts_id]["data"] = column_threshold_check(ts, ts, flag_column, error_code, "==", flag_name)

    return ts_ids


def spike_check(
    ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]], ts_id: str, flag_column: str, flag_name: str, gt: float
) -> TimeSeries:
    """Assess the total difference between a value and its neighbours and remove any skew in the size of the
    differences with each neighbour.

    Note that first and last value in the timeseries cannot be assessed, as they don't have previous/next values to
    assess spike against.

    Args:
        ts_ids: Metadata and data for TimeSeries ids.
        ts_id: The ID of the TimeSeries to check.
        flag_column: The column to which flag value should be added.
        flag_name: The name of the flag to be added to the TimeSeries. This is the method name in the qc config.
        gt: The minimum value for the spike threshold.

    Returns:
        ts_ids: Metadata and data for TimeSeries with the quality control flag applied.
    """
    # Get data
    ts = ts_ids[ts_id]["data"]

    # Make a new dataframe for doing data shifting
    tst_spikes = ts[ts.column_name].df.clone()

    # Difference between value and previous value
    tst_spikes = tst_spikes.with_columns(pl.col(ts.column_name).shift(1).alias("prev_val"))
    tst_spikes = tst_spikes.with_columns((pl.col(ts.column_name).sub(pl.col("prev_val"))).alias("diff_prev"))

    # Difference between next value and value
    tst_spikes = tst_spikes.with_columns(pl.col(ts.column_name).shift(-1).alias("next_val"))
    tst_spikes = tst_spikes.with_columns((pl.col("next_val").sub(pl.col(ts.column_name))).alias("diff_next"))

    # Calculate overall combined difference, absolute value
    tst_spikes = tst_spikes.with_columns((pl.col("diff_prev").sub(pl.col("diff_next"))).abs().alias("d"))

    # Calculate the absolute skew in differences each side of the data value.
    tst_spikes = tst_spikes.with_columns((pl.col("diff_prev").abs().sub(pl.col("diff_next").abs())).abs().alias("skew"))

    # Calculate the total difference minus the skew
    tst_spikes = tst_spikes.with_columns((pl.col("d").sub(pl.col("skew"))).alias("d_no_skew"))

    # As we have summed the differences, we should double the threshold
    spikes = tst_spikes.get_column("d_no_skew").gt(gt * 2.0)

    # Apply the flag to the data
    ts.add_flag(flag_column, flag_name, spikes)

    ts_ids[ts_id]["data"] = ts

    return ts_ids


def radiometer_ta_check(
    ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]],
    ts_id: str,
    flag_column: str,
    flag_name: str,
    gt: float,
    lt: float,
    dep_ts: str,
) -> TimeSeries:
    """Check radiometer temperature values falls between min and max range, applying a quality control flag if
    outside of range.

    Min and max range values are defined per site, per variable and per time resolution.

    Args:
        ts_ids: Metadata and data for TimeSeries ids.
        ts_id: The ID of the TimeSeries to check.
        flag_column: The column to which flag value should be added.
        flag_name: The name of the flag to be added to the TimeSeries. This is the method name in the qc config.
        gt: The minimum value for the range.
        lt: The maximum value for the range.
        dep_ts: The name of the dependent time series to use for the radiometer temperature check.

    Returns:
         ts_ids: Metadata and data for TimeSeries with the quality control flag applied.
    """
    # Get data
    ts = ts_ids[ts_id]["data"]

    # TODO: Fill in this placeholder for radiometer temperature check
    ts_ids[ts_id]["data"] = ts

    return ts_ids


def heat_flux_plate_check(
    ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]],
    ts_id: str,
    flag_column: str,
    flag_name: str,
    time_ge: time,
    time_le: time,
) -> TimeSeries:
    """Removes G1 and G2 for 0:30 and 1:00 while plates are heating up to calibrate

    Args:
        ts_ids: Metadata and data for TimeSeries ids.
        ts_id: The ID of the TimeSeries to check.
        flag_column: The column to which flag value should be added.
        flag_name: The name of the flag to be added to the TimeSeries. This is the method name in the qc config.
        time_ge: The minimum time to remove data from.
        time_le: The maximum time to remove data from.

    Returns:
         ts_ids: Metadata and data for TimeSeries with the quality control flag applied.
    """
    # Get data
    ts = ts_ids[ts_id]["data"]

    # TODO: Fill in this placeholder
    return ts


def pluvio_diagnostic_check(
    ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]],
    ts_id: str,
    flag_column: str,
    flag_name: str,
    gt: float,
    dep_ts: str
) -> TimeSeries:
    """Check the pluvio diagnostic values are no larger than given value.

    Args:
        ts_ids: Metadata and data for TimeSeries ids.
        ts_id: The ID of the TimeSeries to check.
        flag_column: The column to which flag value should be added.
        flag_name: The name of the flag to be added to the TimeSeries. This is the method name in the qc config.
        gt: The maximum value for the diagnostic check.

    Returns:
        The TimeSeries with the quality control flag applied.
    """
    ts = ts_ids[ts_id]["data"]

    # Check if the dependent time series exists
    if dep_ts not in ts_ids:
        raise ValueError(f"Dependent Precip Diag time series '{dep_ts}' not found in ts_ids.")
    diag_ts = ts_ids[dep_ts]["data"]

    ts_ids[ts_id]["data"] = column_threshold_check(ts, diag_ts, flag_column, gt, ">", flag_name)

    return ts_ids


def snow_distance_signal_check(
    ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]],
    ts_id: str,
    flag_column: str,
    flag_name: str,
    lt: float,
    dep_ts: str
) -> TimeSeries:
    """Check the snow distance signal values are no smaller than given value.

    Args:
        ts_ids: Metadata and data for TimeSeries ids.
        ts_id: The ID of the TimeSeries to check.
        flag_column: The column to which flag value should be added.
        flag_name: The name of the flag to be added to the TimeSeries. This is the method name in the qc config.
        lt: The minimum value for the snow distance signal.

    Returns:
        The TimeSeries with the quality control flag applied.
    """
    ts = ts_ids[ts_id]["data"]

    # Check if the dependent time series exists
    if dep_ts not in ts_ids:
        raise ValueError(f"Dependent Snow Signal time series '{dep_ts}' not found in ts_ids.")
    sig_ts = ts_ids[dep_ts]["data"]

    ts_ids[ts_id]["data"] = column_threshold_check(ts, sig_ts, flag_column, lt, "<", flag_name)

    return ts_ids


# def tdt_soil_temp_check(
#     ts: TimeSeries, column: str, flag_column: str, flag_name: str, lt: float, dep_ts: str
# ) -> TimeSeries:
#     """Check the TDT soil temperature values are no smaller than given value and flag VWC readings
#     if so.

#     Args:
#         ts: The input TimeSeries containing the data to be tested.
#         column: The name of the column to which the quality control flag will be applied.
#         flag_column: The column to which flag value should be added.
#         flag_name: The name of the flag to be added to the TimeSeries. This is the method name in the qc config.
#         lt: The minimum temp for the soil.

#     Returns:
#          The TimeSeries with the quality control flag applied.
#     """
#     # TODO: Use alternative TDT if soil temperature is not available or incorrect.
#     # TODO: use dep_ts to get the "TDT#_TSOIL" column. To do this we need TDT#_TSOIL to be loaded
#     # as dependant ts_id in the metadata. FPM-359
#     ts = column_threshold_check(ts, "TDT1_TSOIL", flag_column, lt, "<", flag_name)

#     return ts


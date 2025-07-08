import logging
from datetime import datetime
from typing import Dict, Union

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.__metadata__.config_corrections import corrections_config
from dritimeseriesprocessor.flagging.flagger import corrs_flag_column_name, update_corrections_core_flags
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.corrections.operations import CORRECTION_METHODS
from dritimeseriesprocessor.utils import not_missing_expr

logger = logging.getLogger(__name__)


CORRS_FLAG_SYS_NAME = "corrs_flags"


@metrics.track_corrections_time()
def run_corrections(
    ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]],
) -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
    """Corrects the data by applying a series of corrections based on predefined configurations.

    Args:
        ts_ids: Metadata and data for timeseries ids

    Returns:
        ts_ids: Metadata and corrected data for timeseries ids
    """
    corrs_flags_dict = {method.method_id: method.id for method in corrections_config.correction_methods}
    if not corrs_flags_dict:
        logger.warning("No correction methods given in config.")
        return ts_ids

    for ts_id, ts_dict in ts_ids.items():
        ts = ts_dict["data"]

        for correction_config in corrections_config.corrections:
            if correction_config.site_id != ts.site_id:
                continue

            # Check the target variable exists in the TimeSeries DataFrame
            if correction_config.variable not in ts.data_columns:
                continue

            # Check if the correction method is implemented
            correction_fn = CORRECTION_METHODS.get(correction_config.method_id)
            if not correction_fn:
                logger.warning(f"Unimplemented method: {correction_config.method_id}")
                continue

            # Initialise corrections flag system within TimeSeries object.
            if CORRS_FLAG_SYS_NAME not in ts.flag_systems:
                ts.add_flag_system(CORRS_FLAG_SYS_NAME, corrs_flags_dict)

            # Add a flag column for the correction method
            corrs_flag_col = corrs_flag_column_name(correction_config.variable)
            if corrs_flag_col not in ts.columns:
                ts.init_flag_column(CORRS_FLAG_SYS_NAME, corrs_flag_col)

            # Ensure the end datetime is set; default to the current time if not provided
            if correction_config.end_datetime is None:
                correction_config.end_datetime = datetime.now()

            # Create a mask to filter rows based on SITE_ID and the time range
            mask = (pl.col(ts.time_name) >= correction_config.start_datetime) & (
                pl.col(ts.time_name) <= correction_config.end_datetime
            )

            # Apply the specified correction function to the DataFrame
            logger.info(
                f"Applying correction for {ts_id}: {correction_config.method_id} "
                f"{correction_config.start_datetime} to {correction_config.end_datetime}"
            )
            ts.df = correction_fn(ts.df, correction_config.variable, correction_config.correction_factor, mask)

            # Apply flagging to the DataFrame.
            expr = mask & not_missing_expr(correction_config.variable)
            ts.add_flag(corrs_flag_col, correction_config.method_id, expr)

        ts = update_corrections_core_flags(ts)

    return ts_ids

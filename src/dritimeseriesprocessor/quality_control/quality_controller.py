import logging
from functools import lru_cache
from typing import Dict

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.flagging.flagger import qc_flag_column_name, update_quality_control_core_flags
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.timeseries_container import TimeseriesContainer
from metadata_manager.models.service import load_methods

logger = logging.getLogger(__name__)


QC_FLAG_SYS_NAME = "qc_flags"


@lru_cache(maxsize=1)
def get_qc_methods() -> Dict:
    """Load the qc methods and cache the results."""
    return load_methods("quality_control")


def remove_qcd_data(df: pl.DataFrame, column: str, flag_column: str) -> pl.DataFrame:
    """
    Remove values that have a QC flag for given column.

    Args:
        df: Dataframe containing data and QC flag column
        column: Name data column
        flag_column: Name of QC flag column

    Returns:
        pl.DataFrame with QC'd data removed
    """
    # Remove data
    return df.with_columns(pl.when(pl.col(flag_column) > 0).then(None).otherwise(pl.col(column)).alias(column))


@metrics.track_qc_time()
def run_quality_control(ts_ids: Dict[str, TimeseriesContainer], remove: bool = False) -> Dict[str, TimeseriesContainer]:
    """Run data through Quality Control (QC) checks.

    Applies a series of quality control checks to the input DataFrame based on
    the configuration specified in the qc_config module.

    Args:
        ts_ids: Metadata and data for timeseries ids
        remove: Whether to remove any QC'd data

    Returns:
        ts_ids: Metadata and quality controlled data for timeseries ids
    """
    qc_methods = get_qc_methods()

    # Initialise quality control flag system within ts.TimeFrame object
    qc_flags_dict = {method: method_config.method_id for method, method_config in qc_methods.items()}
    if not qc_flags_dict:
        logger.warning("No QC methods given in config.")
        return ts_ids

    for ts_id, ts_container in ts_ids.items():
        tf = ts_container.data

        if not ts_container.qc_configs:
            logger.info(f"No quality control config found for Time Series ID: {ts_id}")
            continue

        # Set up the flag system if it doesn't already exist
        try:
            tf.get_flag_system(QC_FLAG_SYS_NAME)
        except ts.exceptions.FlagSystemNotFoundError:
            tf.register_flag_system(QC_FLAG_SYS_NAME, qc_flags_dict)

        # Add a flag column for the quality control method
        qc_flag_col = qc_flag_column_name(tf.metadata["column_name"])
        if qc_flag_col not in tf.flag_columns:
            tf.init_flag_column(tf.metadata["column_name"], QC_FLAG_SYS_NAME, qc_flag_col)

        for data_processing_config in ts_container.qc_configs:
            # Run QC methods on time series
            for qc_config in data_processing_config.configs:
                logger.info(f"Quality controlling {ts_id}: {qc_config.name}. Constraints: {qc_config.parameters}")

                qc_method_metadata = qc_methods[qc_config.name]

                # Determine which time series we are running the qc test on
                qc_tf = tf
                if "dep_ts" in qc_config.parameters:
                    # Check if the dependency time series exists
                    if qc_config.parameters["dep_ts"] not in ts_ids:
                        logger.warning(f"Dependency time series {qc_config.parameters['dep_ts']} not found in ts_ids.")
                        continue

                    qc_tf = ts_ids[qc_config.parameters["dep_ts"]].data
                    # No longer need this key in the parameters once we've got the dependency time series
                    qc_config.parameters.pop("dep_ts")

                if qc_method_metadata.arg_mapping:
                    for old_name, new_name in qc_method_metadata.arg_mapping.items():
                        qc_config.parameters[new_name] = qc_config.parameters.pop(old_name)

                if qc_method_metadata.kwargs:
                    for parameter, value in qc_method_metadata.kwargs.items():
                        qc_config.parameters[parameter] = value

                qc_result = qc_tf.qc_check(
                    qc_method_metadata.function_name,
                    column_name=qc_tf.metadata["column_name"],
                    observation_interval=qc_config.observation_interval,
                    **qc_config.parameters,
                )

                # flag the primary time series with the results
                tf.add_flag(qc_flag_col, qc_config.name, qc_result)

                # remove the data that has been flagged if required
                if remove:
                    tf = tf.with_df(remove_qcd_data(tf.df, tf.metadata["column_name"], qc_flag_col))
                    ts_ids[ts_id].data = tf

        tf = update_quality_control_core_flags(tf)

        qcflag_columns = [col for col in tf.columns if col.endswith("_QCFLAG")]
        flags_count = len(qcflag_columns)
        logger.info(f"Number of QC flag columns: {flags_count}")
        metrics.increment_flags(flags_count)

    return ts_ids

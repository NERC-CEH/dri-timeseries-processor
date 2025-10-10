import logging
import re
from functools import lru_cache
from typing import Dict

import polars as pl
import time_stream as ts
from driutils.metadata_api.utils import URI_ID_EXTRACT_REGEX
from time_stream.utils import get_date_filter

from dritimeseriesprocessor.correcting.operations import Operation
from dritimeseriesprocessor.flagging.flagger import corrs_flag_column_name, update_corrections_core_flags
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.timeseries_container import TimeseriesContainer
from dritimeseriesprocessor.utils import extract_dep_ts, not_missing_expr
from metadata_manager.models.schemas.data_processing_configurations import (
    ConfigItem,
)
from metadata_manager.models.service import load_methods, load_site_metadata

logger = logging.getLogger(__name__)

CORRS_FLAG_SYS_NAME = "corrs_flags"


@lru_cache(maxsize=1)
def get_correction_methods() -> Dict:
    """Load the correction methods and cache the results."""
    return load_methods("correction")


@metrics.track_corrections_time()
def run_corrections(
    ts_ids: Dict[str, TimeseriesContainer],
) -> Dict[str, TimeseriesContainer]:
    """Corrects the data by applying a series of corrections based on predefined configurations.

    Args:
        ts_ids: Metadata and data for timeseries ids

    Returns:
        ts_ids: Metadata and corrected data for timeseries ids
    """
    correction_methods = get_correction_methods()

    # Initialise corrections flag system within ts.TimeFrame object
    correction_flags_dict = {method: method_config.method_id for method, method_config in correction_methods.items()}
    if not correction_flags_dict:
        logger.warning("No correction methods given in config.")
        return ts_ids

    for ts_id, ts_container in ts_ids.items():
        tf = ts_container.data

        if not ts_container.correction_configs:
            logger.info(f"No correction config found for Time Series ID: {ts_id}")
            continue

        # Initialise correction flag system within ts.TimeFrame object.
        try:
            tf.get_flag_system(CORRS_FLAG_SYS_NAME)
        except ts.exceptions.FlagSystemNotFoundError:
            tf.register_flag_system(CORRS_FLAG_SYS_NAME, correction_flags_dict)

        # Add a flag column for the correction method
        corrs_flag_col = corrs_flag_column_name(tf.metadata["column_name"])
        if corrs_flag_col not in tf.columns:
            tf.init_flag_column(tf.metadata["column_name"], CORRS_FLAG_SYS_NAME, corrs_flag_col)

        for correction_config in ts_container.correction_configs:
            correction_config.configs = [
                update_config_item_with_site_attributes(config_item=config_item, site_id=correction_config.site_id)
                for config_item in correction_config.configs
            ]

            # Run the corrections on the timeseries
            for corr_config in correction_config.configs:
                if corr_config.observation_interval:
                    date_filter = get_date_filter(tf.time_name, corr_config.observation_interval)
                else:
                    date_filter = pl.lit(True)

                # Only apply the correction if there is data in the observation interval
                if tf.df.filter(date_filter).is_empty():
                    logger.info(
                        f"No data in observation interval {corr_config.observation_interval} for "
                        f"Time Series ID: {ts_id}, skipping correction {corr_config.name}"
                    )
                    continue

                corr_method_metadata = correction_methods.get(corr_config.name)
                if not corr_method_metadata:
                    raise ValueError(f"Correction method {corr_config.name} not found in methods registry.")

                corr_config_update = extract_dep_ts(corr_config, ts_ids)

                if corr_method_metadata.arg_mapping:
                    # Map argument names to match those expected by the operation, where needed.
                    for old_name, new_name in corr_method_metadata.arg_mapping.items():
                        if old_name in corr_config_update.parameters:
                            corr_config_update.parameters[new_name] = corr_config_update.parameters.pop(old_name)

                # Apply the specified correction function to the DataFrame
                op = Operation.get(corr_method_metadata.function_name, **corr_config_update.parameters)
                tf = op.apply(
                    tf,
                    filter_expr=date_filter,
                )

                # Apply flagging to the DataFrame.
                expr = date_filter & not_missing_expr(tf.metadata["column_name"])
                tf.add_flag(corrs_flag_col, corr_config_update.name, expr)

        tf = update_corrections_core_flags(tf)
        ts_container.data = tf

    return ts_ids


def update_config_item_with_site_attributes(config_item: ConfigItem, site_id: str) -> ConfigItem:
    """
    Update the correct configs with the values for any site parameters required.

    For example, if a config contains a site_parameter value of "ALTITUDE", the metadata for the site
    corresponding to the config will be fetched. The altitude value will be extracted and the
    "site_parameter" key value  pair will be replaced with "altitude": altitude_value.

    Args:
        config_item: List of correction configuration objects.

    Returns:
        config_item: The config item to be updated
        site_id: The ID of the site the configuration applies to.

    """
    # If site_attribute isn't in the config item parameters no changes need to be made to the config item.
    if not config_item.parameters.get("site_attribute"):
        return config_item

    site_id = re.match(URI_ID_EXTRACT_REGEX, site_id).group(1)
    site_metadata = load_site_metadata(site_id)

    # Replace the site attribute entry in the parameter dictionary with the corresponding key-value
    # pair for the attribute itself
    site_attribute_key = config_item.parameters["site_attribute"].lower()
    del config_item.parameters["site_attribute"]
    config_item.parameters[site_attribute_key] = site_metadata.get(site_attribute_key)

    return config_item

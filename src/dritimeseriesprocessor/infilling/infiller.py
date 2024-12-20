import logging

import polars as pl

from dritimeseriesprocessor.__metadata__.config_infilling import get_infill_config
from dritimeseriesprocessor.infilling.methods import INFILL_METHODS
from time_series import TimeSeries

logger = logging.getLogger(__name__)


def infill_flag_column_name(column: str) -> str:
    """
    Return column name of infill flag column for a given variable column.

    Args:
        column (str): The name of the original variable column.

    Returns:
        str: The name of the corresponding infill flag column, formatted as '{column}_INFILL_FLAG'.
    """
    return f"{column}_INFILL_FLAG"


def run_infilling(ts: TimeSeries) -> TimeSeries:
    """Run data through Infilling.

    Reads and applies infill methods for each variable from config.

    Args:
        ts: The input TimeSeries containing the data to be infilled.

    Returns:
        The TimeSeries with infilling and infill flags applied.
    """

    infill_configs = get_infill_config("variables")

    for column in ts.data_columns:
        if column in infill_configs:
            # Get available infill methods for this variable/resolution
            methods = infill_configs[column].get(ts.resolution.iso_duration, infill_configs[column].get("default"))
            if methods is None:
                logger.warning(f"No infill methods for: {column}")
                continue

            # Order by priority
            sorted_methods = sorted(methods.methods, key=lambda x: x.priority)
            for method in sorted_methods:
                infill_func = INFILL_METHODS[method.method_id]
                # Run infill function
                logger.info(f"Infilling {column} with method: {method.method_id}. Constraints: {method.constraints}")
                infl_df = infill_func(ts.df[column], **method.constraints)

                infl_flag_col = infill_flag_column_name(column)

                if infl_flag_col not in ts.supplementary_columns:
                    ts.init_supplementary_column(infl_flag_col, data=None, dtype=pl.String)

                # Merge resulting infill values and method ID into df
                ts.df = ts.df.with_columns(
                    pl.col(column).fill_null(infl_df["value_filled"]).fill_nan(infl_df["value_filled"]).alias(column),
                    infl_df["method_id"].alias(infl_flag_col),
                )

    return ts

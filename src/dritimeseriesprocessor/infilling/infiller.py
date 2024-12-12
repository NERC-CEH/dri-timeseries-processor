import logging

import polars as pl

from dritimeseriesprocessor.__metadata__.config_infilling import get_infill_config
from dritimeseriesprocessor.infilling.methods import INFILL_METHODS
from time_series import TimeSeries

logger = logging.getLogger(__name__)


def run_infilling(ts: TimeSeries) -> TimeSeries:
    """Run data through Infilling.

    Reads and applies infill methods for each variable from config.

    Args:
        ts: The input TimeSeries containing the data to be infilled.

    Returns:
        The TimeSeries with infilling and infill flags applied.
    """

    infill_configs = get_infill_config("variables")

    for col in ts.data_columns:
        if col in infill_configs:
            # Get available infill methods for this variable/resolution
            methods = infill_configs[col].get(ts.resolution, infill_configs[col].get("default"))
            if methods is None:
                logger.warning(f"No infill methods for: {col}")
                continue

            # Order by priority
            sorted_methods = sorted(methods.methods, key=lambda x: x.priority)
            for method in sorted_methods:
                infill_func = INFILL_METHODS[method.method_id]
                # Run infill function
                logger.info(f"Infilling {col} with method: {method.method_id}. Constraints: {method.constraints}")
                infl_df = infill_func(ts.df[col], **method.constraints)

                # Merge resulting infill values and method ID into df
                ts.df = ts.df.with_columns(
                    pl.col(col).fill_null(infl_df["value_filled"]).alias(col),
                    infl_df["method_id"].alias(f"{col}_INFILL_METHOD"),
                )

    return ts

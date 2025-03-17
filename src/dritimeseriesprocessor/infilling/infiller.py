import logging
from typing import Dict, Union

from dritimeseriesprocessor.__metadata__.config_infilling import (
    InfillMethod,
    VariableResolutionMethods,
)
from dritimeseriesprocessor.infilling.methods import INFILL_METHODS
from time_series import TimeSeries

logger = logging.getLogger(__name__)


INFILL_FLAG_SYS_NAME = "infill_flags"


def infill_flag_column_name(column: str) -> str:
    """
    Return column name of infill flag column for a given variable column.

    Args:
        column (str): The name of the original variable column.

    Returns:
        str: The name of the corresponding infill flag column, formatted as '{column}_INFILL_FLAG'.
    """
    return f"{column}_INFILL_FLAG"


def run_infilling(
    ts: TimeSeries,
    infill_var_configs: Union[Dict[str, InfillMethod], Dict[str, Dict[str, VariableResolutionMethods]]],
    infill_method_configs: Union[Dict[str, InfillMethod], Dict[str, Dict[str, VariableResolutionMethods]]],
) -> TimeSeries:
    """Run data through Infilling.

    Reads and applies infill methods for each variable from config.

    Args:
        ts: The input TimeSeries containing the data to be infilled.
        infill_var_configs: The infilling variable configurations.
        infill_method_configs: The infilling method configurations.

    Returns:
        The TimeSeries with infilling and infill flags applied.
    """

    # Initialise infilling flag system within TimeSeries object
    infill_flags_dict = {method: method_config.id for method, method_config in infill_method_configs.items()}
    if infill_flags_dict:
        ts.add_flag_system(INFILL_FLAG_SYS_NAME, infill_flags_dict)
    else:
        logger.warning("No infill methods given in config.")
        return ts

    for column in ts.data_columns:
        if column in infill_var_configs:
            # Get available infill methods for this variable/resolution
            methods = infill_var_configs[column].get(
                ts.resolution.iso_duration, infill_var_configs[column].get("default")
            )
            if methods is None:
                logger.warning(f"No infill methods for: {column}")
                continue

            # Order by priority
            sorted_methods = sorted(methods.methods, key=lambda x: x.priority)
            for method_config in sorted_methods:
                infill_flag_col = infill_flag_column_name(column)

                if infill_flag_col not in ts.flag_columns:
                    ts.init_flag_column(INFILL_FLAG_SYS_NAME, infill_flag_col)

                # Run infill function
                infill_func = INFILL_METHODS[method_config.method]
                logger.info(
                    f"Infilling {column} with method: {method_config.method}. Constraints: {method_config.constraints}"
                )
                ts = infill_func(ts, column, infill_flag_col, **method_config.constraints)

    return ts

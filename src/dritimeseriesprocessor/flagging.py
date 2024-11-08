"""Util functions for managing flag data"""

import logging

from dritimeseriesprocessor.__metadata__.config_core_flags import core_flag_config
from time_series import TimeSeries

logger = logging.getLogger(__name__)


def initialise_core_flags(ts: TimeSeries) -> TimeSeries:
    """Add core flag column to each data column in Timeseries object, using the
    data column name and flag name for new column name.
    Initialise all columns with the "unchecked" flag.

    Args:
        ts: The input TimeSeries object.

    Returns:
        The TimeSeries with the flag columns added
    """
    for data_col in ts.data_col_names:
        ts.add_supp_column(f"{data_col}_FLAG", core_flag_config["unchecked"]["id"])
    return ts

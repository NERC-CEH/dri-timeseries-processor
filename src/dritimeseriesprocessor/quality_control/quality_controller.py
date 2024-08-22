import logging

import polars as pl

from dritimeseriesprocessor.__metadata__.config_quality_control import get_qc_config
from dritimeseriesprocessor.quality_control.checks import QC_CHECKS

logger = logging.getLogger(__name__)


def run_quality_control(df: pl.DataFrame) -> pl.DataFrame:
    """Run data through Quality Control (QC) checks.

    Applies a series of quality control checks to the input DataFrame based on
    the configuration specified in the qc_config module.

    Args:
        df: The input DataFrame containing the data to be quality controlled.

    Returns:
        The DataFrame with quality control flags applied.
    """

    qc_check_configs = get_qc_config("qc_tests")

    for check_id, check_config in qc_check_configs.items():
        check_func = QC_CHECKS.get(check_id)
        if check_func is None:
            logger.warning(f"Unimplemented method: {check_id}")
            continue

        for variable in check_config.variables:
            if variable not in df:
                logger.warning(f"Variable not in DataFrame: {variable}")
                continue

            df = check_func(df, variable, check_config.id)

    return df

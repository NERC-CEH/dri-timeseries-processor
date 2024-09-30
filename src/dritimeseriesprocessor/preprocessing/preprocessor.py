import logging
from datetime import datetime

import polars as pl

from dritimeseriesprocessor.__metadata__.config_preprocessing import preprocessing_config
from dritimeseriesprocessor.preprocessing.operations import preprocessing_corrections

logger = logging.getLogger(__name__)


def run_preprocess(df: pl.DataFrame) -> pl.DataFrame:
    """Preprocesses the DataFrame by applying a series of corrections based on predefined configurations.

    Args:
        df: The input DataFrame that needs preprocessing.

    Returns:
        The preprocessed DataFrame with corrections applied.
    """
    for correction_config in preprocessing_config.corrections:
        # Check if the correction method is implemented
        correction_fn = preprocessing_corrections.get(correction_config.METHOD_ID)
        if not correction_fn:
            logger.warning(f"Unimplemented method: {correction_config.METHOD_ID}")
            continue

        # Check if the target variable exists in the DataFrame
        if correction_config.VARIABLE not in df:
            logger.warning(
                f"Variable {correction_config.VARIABLE} not in DataFrame for method {correction_config.METHOD_ID}"
            )
            continue

        # Ensure the end datetime is set; default to the current time if not provided
        if correction_config.END_DATETIME is None:
            correction_config.END_DATETIME = datetime.now()

        # Create a mask to filter rows based on SITE_ID and the time range
        mask = (
            (pl.col("SITE_ID") == correction_config.SITE_ID)
            & (pl.col("time") >= correction_config.START_DATETIME)
            & (pl.col("time") <= correction_config.END_DATETIME)
        )

        # Apply the specified correction function to the DataFrame
        df = correction_fn(df, correction_config, mask)

    return df

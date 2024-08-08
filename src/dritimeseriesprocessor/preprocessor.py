import logging

import polars as pl

from dritimeseriesprocessor.__metadata__.config_preprocessing import preprocessing_config, Correction

logger = logging.getLogger(__name__)


def multiply(df: pl.DataFrame, p_config: Correction) -> pl.DataFrame:
    corrected = df[p_config.VARIABLE] * p_config.CORRECTION_FACTOR
    return corrected


preprocessing_operations = {
    "MULTIPLY": multiply
}


def preprocess(df: pl.DataFrame) -> pl.DataFrame:
    for correction_config in preprocessing_config.corrections:
        if correction_config.METHOD_ID not in preprocessing_operations:
            logger.warning(f'Unimplemented method: {correction_config.METHOD_ID}')
            continue

        if correction_config.VARIABLE not in df:
            logger.warning(f'Variable not in DataFrame: {correction_config.VARIABLE}')
            continue

        mask = (
                (pl.col("SITE_ID") == correction_config.SITE_ID) &
                (pl.col("time") >= correction_config.START_DATETIME) &
                (pl.col("time") <= correction_config.END_DATETIME)
        )

        df = df.with_columns([
            pl.when(mask)
              .then(preprocessing_operations[correction_config.METHOD_ID](df, correction_config))
              .otherwise(pl.col(correction_config.VARIABLE))
        ])

    return df

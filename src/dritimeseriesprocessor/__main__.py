import logging
from datetime import date

import polars as pl

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.preprocessing.preprocessor import run_preprocess
from dritimeseriesprocessor.quality_control.quality_controller import run_quality_control
from dritimeseriesprocessor.s3_crud import data_manager

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger("dritimeseriesprocessor")

# Get data
prefix = "cosmos/PRECIP_1MIN_2024_LOOPED"
start_date = date(2024, 1, 30)
end_date = None
data = data_manager.query_by_date_range(
    app_config.level_0_bucket,
    prefix,
    start_date,
    end_date,
    site_ids="ALIC1",
    columns=["time", "SITE_ID", "P_BUCKET_RT", "P_LOADCELL_TEMP"],
)

# Preprocessing
preprocessed_data = run_preprocess(data)

# Quality control

# dummy some data that will force some qc checks to run
preprocessed_data = preprocessed_data.with_columns(
    [
        pl.Series([0 if ((i // 20) % 2 == 0) else 100 for i in range(len(preprocessed_data))]).alias("BATTV"),
        pl.Series(i * 2 for i in range(len(preprocessed_data))).alias("PRECIP"),
    ]
)
qcd_data = run_quality_control(preprocessed_data)

# show first 100 rows to show how qc flags have been applied
with pl.Config(tbl_rows=100):
    logger.info(qcd_data.limit(100))

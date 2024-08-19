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

# dummy some BATTV data
preprocessed_data = preprocessed_data.with_columns(
    pl.Series(i for i in range(0, len(preprocessed_data))).alias("BATTV")
)
qcd_data = run_quality_control(preprocessed_data)

logger.info(qcd_data)

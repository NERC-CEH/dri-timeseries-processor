import logging
import os
from datetime import date

import boto3
import polars as pl

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.logger import setup_logging
from dritimeseriesprocessor.preprocessing.preprocessor import run_preprocess
from dritimeseriesprocessor.quality_control.quality_controller import run_quality_control
from dritimeseriesprocessor.s3_crud import data_manager
from dritimeseriesprocessor.s3_crud.write import S3Writer

setup_logging()

logger = logging.getLogger(__name__)

# Get S3 Client
if "environment" not in os.environ:
    s3_client = boto3.client("s3", endpoint_url=app_config.endpoint_url)
else:
    s3_client = boto3.client("s3")

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

logger.info(f"Retrieved data from s3: {data.shape}")

# Preprocessing
preprocessed_data = run_preprocess(data)

logger.info(f"Ran preprocessor successfully, shape: {preprocessed_data.shape}")

# Quality control
# dummy some data that will force some qc checks to run
preprocessed_data = preprocessed_data.with_columns(
    [
        pl.Series([0 if ((i // 20) % 2 == 0) else 100 for i in range(len(preprocessed_data))]).alias("BATTV"),
        pl.Series(i * 2 for i in range(len(preprocessed_data))).alias("PRECIP"),
        pl.Series([5 if (i != 5) else 50 for i in range(len(preprocessed_data))]).alias("TA"),
        pl.Series(i for i in range(len(preprocessed_data))).alias("SCANS"),
    ]
)

logger.info(f"Added dummy data to preprocessed data, shape: {preprocessed_data.shape}")

qcd_data = run_quality_control(preprocessed_data)

# show first 100 rows to show how qc flags have been applied
with pl.Config(tbl_rows=100):
    logger.info(qcd_data.limit(100))

# Writing output
writer = S3Writer(s3_client)
writer.write(
    bucket_name=app_config.qc_bucket,
    key=f"cosmos/30min/{writer._build_date_range_key(start_date, end_date)}.parquet",
    body=qcd_data,
)

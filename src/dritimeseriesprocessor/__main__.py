import logging
import os
from datetime import date

import boto3

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.preprocessing.preprocessor import preprocess
from dritimeseriesprocessor.quality_control.quality_control import run_qc
from dritimeseriesprocessor.s3_crud import data_manager
from dritimeseriesprocessor.s3_crud.write import S3Writer

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger("dritimeseriesprocessor")

# Get S3 Client
if "environment" not in os.environ:
    s3_client = boto3.client("s3", endpoint_url=app_config.endpoint_url)
else:
    s3_client = boto3.client("s3")
# Get data
prefix = "cosmos/SOILMET_30MIN_2024_LOOPED"
start_date = date(2024, 1, 1)
end_date = date(2024, 1, 31)
# end_date = None
data = data_manager.query_by_date_range(app_config.level_0_bucket, prefix, start_date, end_date, site_ids="BUNNY")

# Preprocessing
preprocessed_data = preprocess(data)

logger.info(preprocessed_data.count())
logger.info(preprocessed_data)

# Quality control
qcd_data = run_qc(preprocessed_data)

logger.info(qcd_data.count())
logger.info(qcd_data)

# Writing output
writer = S3Writer(s3_client)
writer.write(
    bucket_name=app_config.qc_bucket,
    key=f"cosmos/30min/{writer._build_key(start_date, end_date)}.parquet",
    body=qcd_data,
)

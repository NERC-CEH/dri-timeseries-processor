import logging
from datetime import date

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.preprocessing.preprocessor import preprocess
from dritimeseriesprocessor.quality_control.quality_control import run_qc
from dritimeseriesprocessor.s3_crud import data_manager

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger("dritimeseriesprocessor")

# Get Parquet Reader
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

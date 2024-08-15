import logging
from datetime import date

from dritimeseriesprocessor import quality_control
from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.preprocessing.preprocessor import preprocess
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
preprocessed_data = preprocess(data)

logger.info(preprocessed_data.count())
logger.info(preprocessed_data)

# Quality control
qcd_data = quality_control.run_qc(preprocessed_data)

logger.info(qcd_data.count())
logger.info(qcd_data)

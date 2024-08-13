import logging
from datetime import date

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.preprocessing.preprocessor import preprocess
from dritimeseriesprocessor.s3_crud import data_manager

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

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

# Do preprocessing
preprocessed_data = preprocess(data)

logger.info(preprocessed_data)

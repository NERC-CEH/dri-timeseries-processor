import logging
from datetime import date

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.s3_crud import data_manager

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# Get data
data_category = "SOILMET_1MIN"
start_date = date(2024, 1, 17)
end_date = date(2024, 1, 21)
data = data_manager.read_by_date_range(app_config.level_0_bucket, data_category, start_date, end_date, site_ids="BUNNY")

logger.info(data.count())
logger.info(data)

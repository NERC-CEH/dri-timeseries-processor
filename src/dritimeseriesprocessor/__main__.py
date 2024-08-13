import logging
from datetime import date

from dritimeseriesprocessor import quality_control
from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.s3_crud import data_manager

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# Get data
data_category = "PRECIP_1MIN_2024_LOOPED"
start_date = date(2024, 1, 17)
end_date = date(2024, 1, 17)
data = data_manager.query_by_date_range(
    app_config.level_0_bucket, data_category, start_date, end_date, site_ids="BUNNY"
)

# Preprocessing here

# Quality control
qcd_data = quality_control.run_qc(data)

logger.info(qcd_data.count())
logger.info(qcd_data)

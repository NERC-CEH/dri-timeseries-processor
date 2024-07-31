import logging
from pathlib import Path

from dritimeseriesprocessor import filter_config_validation, read_parquet
from dritimeseriesprocessor.configuration import app_config

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

bucket = app_config.level_0_bucket
filter_config_path = (
    str(Path(Path(__file__).parents[0], "__assets__", app_config.filter_config_path))
)

# Validate filter config
filter_config = filter_config_validation.validate(filter_config_path)

# Get data
data = read_parquet.read_parquet_by_config(bucket, filter_config)

logger.info(data.count())
logger.info(data)

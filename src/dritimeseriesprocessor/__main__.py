import logging

from dritimeseriesprocessor import read_parquet
from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.validation import validate_filter_config

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

bucket = app_config.level_0_bucket
filter_config_path = app_config.filter_config_path

data = read_parquet.read_parquet_by_config(bucket, filter_config_path)

logger.info(data.count())
logger.info(data)

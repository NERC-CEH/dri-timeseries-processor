import logging
from datetime import date

from dritimeseriesprocessor import parquet_access
from dritimeseriesprocessor.configuration import app_config

logging.basicConfig(level=logging.INFO)

bucket = app_config.level_0_bucket
filter_config = {
    'BUNNY': (date(2024, 1, 1), date(2024, 1, 7)),
    'BUNNY': (date(2024, 1, 1), date(2024, 1, 7))
}

df = parquet_access.get_parquet_by_dates(bucket, filter_config)

print(df.count())

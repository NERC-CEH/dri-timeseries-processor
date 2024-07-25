import logging
from datetime import date

from dritimeseriesprocessor import parquet_access
from dritimeseriesprocessor.configuration import app_config

logging.basicConfig(level=logging.INFO)

start_date = date(2024, 1, 1)
end_date = date(2024, 1, 7)
df = parquet_access.get_parquet_by_dates(app_config.level_0_bucket, start_date, end_date)

print(df)

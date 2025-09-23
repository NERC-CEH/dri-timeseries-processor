from datetime import date, datetime

import polars as pl

from dritimeseriesprocessor.s3_crud.data_manager import query_by_date_range
from dritimeseriesprocessor.utils import sterilize_dates
from testing.utils.s3_test_helper import S3TestHelper

BUCKET_NAME = "ukceh-fdri-staging-timeseries-level-0"


class TestReadByDateRange:
    """Test the data is read correctly."""

    def test_read_by_date_range_no_site_ids(self, s3_test_helper: S3TestHelper) -> None:
        """Test reading data when no site_ids added to command line.

        This means all sites are read.
        """
        s3_test_helper._create_hourly_test_data(datetime(2024, 1, 1), datetime(2024, 1, 10), upload=True)

        start_date, end_date = sterilize_dates(date(2024, 1, 1), date(2024, 1, 4))

        expected_site_ids = ["site1", "site2"]
        expected_datetimes = pl.datetime_range(start=start_date, end=end_date, interval="1h", eager=True).to_list()

        result = query_by_date_range(
            bucket_name=BUCKET_NAME,
            prefix="cosmos/dataset=test_dataset",
            start_date=start_date,
            end_date=end_date,
            site_ids=["site1", "site2"],
        )
        result_site_ids = result["SITE_ID"].unique().to_list()
        result_datetimes = result["time"].unique().to_list()

        assert isinstance(result, pl.DataFrame)
        assert sorted(result_site_ids) == expected_site_ids
        assert sorted(result_datetimes) == expected_datetimes
        assert result.shape == (384, 7)

    def test_read_by_date_range_with_site_ids(self, s3_test_helper: S3TestHelper) -> None:
        """Test reading data when specifying site IDs."""
        s3_test_helper._create_hourly_test_data(datetime(2024, 1, 1), datetime(2024, 1, 10), upload=True)

        start_date, end_date = sterilize_dates(date(2024, 1, 3), date(2024, 1, 7))

        expected_site_ids = ["site1"]
        expected_datetimes = pl.datetime_range(start=start_date, end=end_date, interval="1h", eager=True).to_list()

        result = query_by_date_range(
            bucket_name=BUCKET_NAME,
            prefix="cosmos/dataset=test_dataset",
            start_date=start_date,
            end_date=end_date,
            site_ids=["site1"],
        )
        result_site_ids = result["SITE_ID"].unique().to_list()
        result_datetimes = result["time"].unique().to_list()

        assert isinstance(result, pl.DataFrame)
        assert sorted(result_site_ids) == expected_site_ids
        assert sorted(result_datetimes) == expected_datetimes
        assert result.shape == (240, 7)

    def test_read_by_date_range_with_selected_columns(self, s3_test_helper: S3TestHelper) -> None:
        """Test reading data when specifying specific columns"""
        s3_test_helper._create_hourly_test_data(datetime(2024, 1, 1), datetime(2024, 1, 10), upload=True)

        cols = ["col1"]
        start_date, end_date = sterilize_dates(date(2024, 1, 1), date(2024, 1, 10))

        expected_datetimes = pl.datetime_range(start=start_date, end=end_date, interval="1h", eager=True).to_list()

        result = query_by_date_range(
            bucket_name=BUCKET_NAME,
            prefix="cosmos/dataset=test_dataset",
            start_date=start_date,
            end_date=end_date,
            site_ids=["site1"],
            columns=cols,
        )
        result_datetimes = result["time"].unique().to_list()

        assert isinstance(result, pl.DataFrame)
        assert result.shape == (480, 2)
        assert sorted(result_datetimes) == expected_datetimes
        assert result.columns == ["time", "col1"]

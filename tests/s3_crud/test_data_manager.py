from datetime import date

import polars as pl
import unittest

from dritimeseriesprocessor.s3_crud.data_manager import query_by_date_range
from dritimeseriesprocessor.utils import steralize_dates
from tests.s3_crud.base_test_case import BaseTestCase


class TestReadByDateRange(BaseTestCase):
    def test_read_by_date_range_no_site_ids(self):
        """Test reading data without specifying site IDs.
        """
        start_date, end_date = steralize_dates(date(2024, 1, 1), date(2024, 1, 4))
        
        expected_site_ids = ['site1', 'site2']
        expected_datetimes = pl.datetime_range(start=start_date, end=end_date, interval="1h", eager=True).to_list()

        result = query_by_date_range(
            bucket_name=self.bucket_name,
            prefix='TEST_CATEGORY',
            start_date=start_date,
            end_date=end_date
        )
        result_site_ids = result['SITE_ID'].unique().to_list()
        result_datetimes = result['time'].unique().to_list()

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(sorted(result_site_ids), expected_site_ids)
        self.assertEqual(sorted(result_datetimes), expected_datetimes)
        self.assertEqual(result.shape, (192, 5))

    def test_read_by_date_range_with_site_ids(self):
        """Test reading data when specifying site IDs.
        """
        start_date, end_date = steralize_dates(date(2024, 1, 3), date(2024, 1, 7))

        expected_site_ids = ['site1']
        expected_datetimes = pl.datetime_range(start=start_date, end=end_date, interval="1h", eager=True).to_list()

        result = query_by_date_range(
            bucket_name=self.bucket_name,
            prefix='TEST_CATEGORY',
            start_date=start_date,
            end_date=end_date,
            site_ids='site1'
        )
        result_site_ids = result['SITE_ID'].unique().to_list()
        result_datetimes = result['time'].unique().to_list()

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(sorted(result_site_ids), expected_site_ids)
        self.assertEqual(sorted(result_datetimes), expected_datetimes)
        self.assertEqual(result.shape, (120, 5))

    def test_read_by_date_range_with_selected_columns(self):
        """Test reading data when specifying specific columns
        """
        cols = ['time', 'SITE_ID', 'col1']
        start_date, end_date = steralize_dates(date(2024, 1, 1), date(2024, 1, 10))

        expected_site_ids = ['site1', 'site2']
        expected_datetimes = pl.datetime_range(start=start_date, end=end_date, interval="1h", eager=True).to_list()
        
        result = query_by_date_range(
            bucket_name=self.bucket_name,
            prefix='TEST_CATEGORY',
            start_date=start_date,
            end_date=end_date,
            columns=cols
        )
        result_site_ids = result['SITE_ID'].unique().to_list()
        result_datetimes = result['time'].unique().to_list()

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(result.shape, (480, 3))
        self.assertEqual(sorted(result_site_ids), expected_site_ids)
        self.assertEqual(sorted(result_datetimes), expected_datetimes)
        self.assertEqual(result.columns, cols)

if __name__ == "__main__":
    unittest.main()
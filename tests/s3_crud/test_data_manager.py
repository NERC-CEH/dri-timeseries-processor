import unittest
from datetime import date, datetime

import polars as pl

from dritimeseriesprocessor.s3_crud.data_manager import configure_dates, configure_site_ids, read_by_date_range
from tests.s3_crud.base_test_case import BaseTestCase


class TestConfigureDates(unittest.TestCase):
    def test_start_date_only(self):
        """Test with only start_date provided as date that datetimes of start and end of that date are returned
        """
        start = date(2023, 8, 1)
        expected_start = datetime.combine(start, datetime.min.time())
        expected_end = datetime.combine(start, datetime.max.time())
        result = configure_dates(start)
        self.assertEqual(result, (expected_start, expected_end))

    def test_start_date_and_end_date_as_dates(self):
        """Test with both start_date and end_date provided as dates that datetimes are returned
        """
        start = date(2023, 8, 1)
        end = date(2023, 8, 10)
        expected_start = datetime.combine(start, datetime.min.time())
        expected_end = datetime.combine(end, datetime.max.time())
        result = configure_dates(start, end)
        self.assertEqual(result, (expected_start, expected_end))

    def test_start_date_after_end_date_error(self):
        """Test with start_date after end_date, should raise UserWarning.
        """
        start = date(2023, 8, 10)
        end = date(2023, 8, 1)
        with self.assertRaises(UserWarning):
            configure_dates(start, end)

    def test_start_date_equals_end_date(self):
        """Test with start_date equal to end_date hat datetimes of start and end of that date are returned.
        """
        start = date(2023, 8, 1)
        end = date(2023, 8, 1)
        expected_start = datetime.combine(start, datetime.min.time())
        expected_end = datetime.combine(end, datetime.max.time())
        result = configure_dates(start, end)
        self.assertEqual(result, (expected_start, expected_end))

    def test_datetime_input(self):
        """Test with datetime inputs for both start_date and end_date."""
        start = datetime(2023, 8, 1, 12, 0)
        end = datetime(2023, 8, 10, 18, 0)
        result = configure_dates(start, end)
        self.assertEqual(result, (start, end))

    def test_mixed_date_and_datetime(self):
        """Test with start_date as date and end_date as datetime."""
        start = date(2023, 8, 1)
        end = datetime(2023, 8, 10, 18, 0)
        expected_start = datetime.combine(start, datetime.min.time())
        result = configure_dates(expected_start, end)
        self.assertEqual(result, (expected_start, end))


class TestConfigureSiteIds(unittest.TestCase):
    def test_none_input(self):
        """Test with None as input, should return an empty list.
        """
        result = configure_site_ids(None)
        self.assertEqual(result, [])

    def test_no_input(self):
        """Test with no input, should return an empty list.
        """
        result = configure_site_ids()
        self.assertEqual(result, [])

    def test_empty_string_input(self):
        """Test with an empty string as input, should return an empty list.
        """
        result = configure_site_ids('')
        self.assertEqual(result, [])

    def test_single_string_input(self):
        """Test with a single site ID as a string.
        """
        result = configure_site_ids('site1')
        self.assertEqual(result, ['site1'])

    def test_list_of_strings_input(self):
        """Test with a list of site IDs.
        """
        result = configure_site_ids(['site1', 'site2', 'site3'])
        self.assertEqual(result, ['site1', 'site2', 'site3'])

    def test_empty_list_input(self):
        """Test with an empty list, should return an empty list.
        """
        result = configure_site_ids([])
        self.assertEqual(result, [])


class TestReadByDateRange(BaseTestCase):
    def test_read_by_date_range_no_site_ids(self):
        """Test reading data without specifying site IDs.
        """
        result = read_by_date_range(
            bucket_name=self.bucket_name,
            data_category='TEST_CATEGORY',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 10)
        )
        result_site_ids = result['SITE_ID'].unique().to_list()

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(sorted(result_site_ids), ['site1', 'site2'])
        self.assertEqual(result.shape, (480, 4))

    def test_read_by_date_range_with_site_ids(self):
        """Test reading data when specifying site IDs.
        """
        result = read_by_date_range(
            bucket_name=self.bucket_name,
            data_category='TEST_CATEGORY',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 10),
            site_ids='site1'
        )
        result_site_ids = result['SITE_ID'].unique().to_list()

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(sorted(result_site_ids), ['site1'])
        self.assertEqual(result.shape, (240, 4))

    def test_read_by_date_range_with_selected_columns(self):
        """Test reading data when specifying specific columns
        """
        result = read_by_date_range(
            bucket_name=self.bucket_name,
            data_category='TEST_CATEGORY',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 10),
            columns=['time', 'SITE_ID', 'col1']
        )

        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(result.shape, (480, 3))
        self.assertEqual(result.columns, ['time', 'SITE_ID', 'col1'])

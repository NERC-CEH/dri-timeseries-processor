import polars as pl
import polars.testing
import unittest
from datetime import date, datetime

from dritimeseriesprocessor import utils


class TestValidateISO8601Duration(unittest.TestCase):
    def test_valid_duration_full_format(self):
        """Test a valid ISO 8601 duration in full format."""
        duration = "P1Y2M3DT4H5M6S"
        self.assertTrue(utils.validate_iso8601_duration(duration))

    def test_valid_duration_days_only(self):
        """Test a valid ISO 8601 duration with days only."""
        duration = "P3D"
        self.assertTrue(utils.validate_iso8601_duration(duration))

    def test_valid_duration_hours_only(self):
        """Test a valid ISO 8601 duration with hours only."""
        duration = "PT4H"
        self.assertTrue(utils.validate_iso8601_duration(duration))

    def test_valid_duration_combination(self):
        """Test a valid ISO 8601 duration with a combination of elements."""
        duration = "P2W"
        self.assertTrue(utils.validate_iso8601_duration(duration))

    def test_invalid_duration_missing_p(self):
        """Test an invalid ISO 8601 duration missing the 'P' character."""
        duration = "1Y2M3DT4H5M6S"
        self.assertFalse(utils.validate_iso8601_duration(duration))

    def test_invalid_duration_wrong_format(self):
        """Test an invalid ISO 8601 duration with a wrong format."""
        duration = "P1Y2M3D4H5M6S"
        self.assertFalse(utils.validate_iso8601_duration(duration))

    def test_invalid_duration_non_iso_string(self):
        """Test an invalid ISO 8601 duration with a non-ISO string."""
        duration = "This is not a duration"
        self.assertFalse(utils.validate_iso8601_duration(duration))

    def test_empty_string(self):
        """Test an invalid ISO 8601 duration with an empty string."""
        duration = ""
        self.assertFalse(utils.validate_iso8601_duration(duration))


class TestRemoveProtocolFromUrl(unittest.TestCase):
    def test_https_url(self):
        """Test removing protocol from an HTTPS URL."""
        url = "https://www.example.com"
        expected = "www.example.com"
        result = utils.remove_protocol_from_url(url)
        self.assertEqual(result, expected)

    def test_http_url(self):
        """Test removing protocol from an HTTP URL."""
        url = "http://www.example.com"
        expected = "www.example.com"
        result = utils.remove_protocol_from_url(url)
        self.assertEqual(result, expected)

    def test_url_with_path(self):
        """Test removing protocol from a URL with a path."""
        url = "https://www.example.com/path/to/resource"
        expected = "www.example.com/path/to/resource"
        result = utils.remove_protocol_from_url(url)
        self.assertEqual(result, expected)

    def test_url_with_port(self):
        """Test removing protocol from a URL with a port."""
        url = "https://www.example.com:8080"
        expected = "www.example.com:8080"
        result = utils.remove_protocol_from_url(url)
        self.assertEqual(result, expected)

    def test_url_without_protocol(self):
        """Test a URL that already has no protocol."""
        url = "www.example.com"
        expected = "www.example.com"
        result = utils.remove_protocol_from_url(url)
        self.assertEqual(result, expected)


class TestSteralizeDates(unittest.TestCase):
    def test_start_date_only(self):
        """Test with only start_date provided as date that datetimes of start and end of that date are returned
        """
        start = date(2023, 8, 1)
        expected_start = datetime.combine(start, datetime.min.time())
        expected_end = datetime.combine(start, datetime.max.time())
        result = utils.steralize_dates(start)
        self.assertEqual(result, (expected_start, expected_end))

    def test_start_date_and_end_date_as_dates(self):
        """Test with both start_date and end_date provided as dates that datetimes are returned
        """
        start = date(2023, 8, 1)
        end = date(2023, 8, 10)
        expected_start = datetime.combine(start, datetime.min.time())
        expected_end = datetime.combine(end, datetime.max.time())
        result = utils.steralize_dates(start, end)
        self.assertEqual(result, (expected_start, expected_end))

    def test_start_date_after_end_date_error(self):
        """Test with start_date after end_date, should raise UserWarning.
        """
        start = date(2023, 8, 10)
        end = date(2023, 8, 1)
        with self.assertRaises(UserWarning):
            utils.steralize_dates(start, end)

    def test_start_date_equals_end_date(self):
        """Test with start_date equal to end_date that datetimes of start and end of that date are returned.
        """
        start = date(2023, 8, 1)
        end = date(2023, 8, 1)
        expected_start = datetime.combine(start, datetime.min.time())
        expected_end = datetime.combine(end, datetime.max.time())
        result = utils.steralize_dates(start, end)
        self.assertEqual(result, (expected_start, expected_end))

    def test_datetime_input(self):
        """Test with datetime inputs for both start_date and end_date."""
        start = datetime(2023, 8, 1, 12, 0)
        end = datetime(2023, 8, 10, 18, 0)
        result = utils.steralize_dates(start, end)
        self.assertEqual(result, (start, end))

    def test_mixed_date_and_datetime(self):
        """Test with start_date as date and end_date as datetime."""
        start = date(2023, 8, 1)
        end = datetime(2023, 8, 10, 18, 0)
        expected_start = datetime.combine(start, datetime.min.time())
        result = utils.steralize_dates(expected_start, end)
        self.assertEqual(result, (expected_start, end))


class TestGroupByDateSiteID(unittest.TestCase):
    """Test the group_by_date_site_id function."""

    def test_group_by_date_site_id(self):
        """Test that df is split correctly."""

        data = {"time": [datetime(2024, 1, 1, 1, 10, 0), datetime(2024, 1, 1, 1, 10, 0), datetime(2024, 1, 2, 1, 10, 0),
                        datetime(2024, 1, 2, 1, 10, 0), datetime(2024, 1, 3, 1, 10, 0), datetime(2024, 1, 3, 1, 10, 0)],
                "SITE_ID": ["site1", "site1", "site1", "site2", "site3", "site3"],
                "value": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]}
        schema = {"time": pl.Datetime, "SITE_ID": pl.String, "value": pl.Float64}

        df = pl.DataFrame(data, schema)

        result = utils.group_by_date_site_id(df)

        # Should be 4 dataframes
        assert(len(result), 4)

        for date, site, data in result:
            expected = df.filter((pl.col('time').dt.date() == date) & (pl.col('SITE_ID') == site))
            polars.testing.assert_frame_equal(data, expected)


class TestMissingExpr(unittest.TestCase):
    def test_missing_expr(self):
        """Test the expression for detecting missing values."""
        expr = utils.missing_expr("value")
        df = pl.DataFrame({"value": [10, None, 30, float('nan'), 50]}, strict=False)
        result = df.with_columns(expr.alias("is_missing"))
        self.assertEqual(result["is_missing"].to_list(), [False, True, False, True, False])


class TestNotMissingExpr(unittest.TestCase):
    def test_not_missing_expr(self):
        """Test the expression for detecting non-missing values."""
        expr = utils.not_missing_expr("value")
        df = pl.DataFrame({"value": [10, None, 30, float('nan'), 50]}, strict=False)
        result = df.with_columns(expr.alias("is_not_missing"))
        self.assertEqual(result["is_not_missing"].to_list(), [True, False, True, False, True])


class TestSplitDataForProcessing(unittest.TestCase):
    """Test the split_data_for_processing function."""

    def test_split_data_for_processing(self):
        """Test that df is split correctly."""

        data = {"time": [datetime(2024, 1, 1, 1, 10, 0), datetime(2024, 1, 1, 1, 10, 0), datetime(2024, 1, 2, 1, 10, 0),
                        datetime(2024, 1, 2, 1, 10, 0), datetime(2024, 1, 3, 1, 10, 0), datetime(2024, 1, 3, 1, 10, 0)],
                "SITE_ID": ["site1", "site1", "site1", "site2", "site3", "site3"],
                "value": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]}
        schema = {"time": pl.Datetime, "SITE_ID": pl.String, "value": pl.Float64}

        df = pl.DataFrame(data, schema)
        metadata = {'test': 'test_metadata'}

        result = utils.split_data_for_processing(df, metadata)

        # Should be 3 dataframes
        assert(len(result), 3)

        for site, data, metadata in result:
            expected = df.filter((pl.col('SITE_ID') == site))
            polars.testing.assert_frame_equal(data, expected)

            self.assertEqual(metadata, {'test': 'test_metadata'})


class TestRemoveSitesNotInStore(unittest.TestCase):
    """Test the remove_sites_not_in_store function."""

    def test_all_sites_in_store(self):
        sites = ['A', 'B']
        metadata_sites = ['A', 'B', 'C']

        result = utils.remove_sites_not_in_store(sites, metadata_sites)

        self.assertEqual(sorted(result), sorted(['A', 'B']))
    
    def test_one_site_not_in_store(self):
        sites = ['A', 'B']
        metadata_sites = ['A']

        with self.assertRaises(ValueError) as err:
            utils.remove_sites_not_in_store(sites, metadata_sites)

        self.assertEqual(str(err.exception), "The following sites ['B'] are not in the metadata store. Remove from '--sites' argument.")


class TestExtractUniqueTimeseriesDefinitions(unittest.TestCase):
    """Test the extract_unique_timeseries_definitions function."""
    test_timeseries_ids = {
        "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-pa_30min_processed":
        {
            "ts_def": "test_a"
        },
        "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-ta_30min_processed":
        {
            "ts_def": "test_b"
        },
        "http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-pa_30min_processed":
        {
            "ts_def": "test_a"
        },
        "http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-ta_30min_processed":
        {
            "ts_def": "test_d",
        }
    }

    expected = ["test_a", "test_b", "test_d"]

    result = utils.extract_unique_timeseries_defs(test_timeseries_ids)

    assert result == expected

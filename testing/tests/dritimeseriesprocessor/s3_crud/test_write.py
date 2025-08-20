from datetime import datetime
from io import BytesIO
from unittest.mock import patch

import moto
import polars as pl
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.s3_crud.write import S3Writer
from testing.utils.s3_test_helper import S3TestHelper
from testing.utils.timeseries_test_helper import TimeSeriesTestHelper

class TestS3Writer(S3TestHelper, TimeSeriesTestHelper):
    """Test the s3 writer class"""

    def setUp(self):
        super().setUp()

        self.writer = S3Writer(self.s3_client)

        self.bucket_name = "ukceh-fdri-staging-timeseries-level-0"
        self.data = self._create_hourly_test_data(datetime(2024, 1, 1), datetime(2024, 1, 10))

    def test_s3_client_type(self):
        """Returns an object if s3_client is of type `boto3.client.s3`, otherwise
        raises an error"""

        # Happy path
        writer = S3Writer(self.s3_client)

        # Bad path
        with self.assertRaises(TypeError):
            S3Writer("not an s3 client")


    def test_s3_key_builder(self, network='network', site_id='BUNNY', resolution = "PT1M", date=datetime(2024, 2, 22, 1, 32, 14)):
        """Tests that the _build_s3_key method returns correctly"""
        
        result = S3Writer._build_s3_key(network, site_id, resolution, date)
        expected = f'network={network}/date=2024-02-22/site={site_id}/resolution={resolution}/data.parquet'
        self.assertEqual(result, expected)


    def test_group_data_by_resolution_and_site(self):
        """Test data correctly grouped by site and resolution."""
        input_filepath = self.input_dir.joinpath("write")
        output_filepath = self.output_dir.joinpath("write", "group_res_site")

        # Load test data into ts_ids structure
        # Test data consists of
        # - Data of the same site and resolution but with different columns and different times
        # (to test dataframes correctly merged)
        # - Data of the same resolution but different sites (to test they are correctly separated)
        test_ts_ids = self.load_ts_ids_from_json_file(input_filepath.joinpath("processed_ts_ids.json"))

        # For write methods we only need processed datasets and their metadata
        processed_timeseries = [
            metadata for metadata in test_ts_ids.values() if metadata["processing_level"] == "processed"]

        result = self.writer._group_data_by_resolution_and_site(processed_timeseries)

        # should be 4 entries in result
        assert len(result) == 4

        # compare dataframes for each output
        for item in result:
            key = f"{item[0]}_{item[1]}.parquet"

            expected = pl.read_parquet(output_filepath.joinpath(key))
            assert_frame_equal(item[2], expected)


    def test_split_by_day(self):
        """Test that data is split correctly."""

        # Use an output from the group_data_by_resolution_and_site test as inputs
        input_filepath = self.output_dir.joinpath("write", "group_res_site")

        # Load test data
        # Just need to test on one dataframe with multiple dates
        test_timeseries = pl.read_parquet(input_filepath.joinpath("PT30M_ALIC1.parquet"))
        
        result = self.writer._split_by_date(test_timeseries)

        # Should be 2 dataframes
        assert len(result) == 2

        for date, data in result:
            expected = test_timeseries.filter((pl.col('time').dt.date() == date))
            assert_frame_equal(data, expected)


class TestMergeDataframes(S3TestHelper):
    """Test the merge dataframes method."""

    def setUp(self):
        super().setUp()

        self.writer = S3Writer(self.s3_client)

    def test_two_matching_dataframes(self):
        """Test updating the existing dataframe when the new one is the same."""
        existing_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_a": [1, 2, 3]
        }
        existing_df = pl.DataFrame(existing_df_data)
        new_df = pl.DataFrame(existing_df_data)
        expected_df = pl.DataFrame(existing_df_data)

        result = self.writer._merge_dataframes(existing_df, new_df)

        assert_frame_equal(result, expected_df)

    def test_additional_column(self):
        """Test unchanged columns from the existing df, and the new column from new df are
        in the output."""
        existing_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_a": [1, 2, 3]
        }

        new_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_b": [1, 2, 3]
        }

        expected_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_a": [1, 2, 3],
            "col_b": [1, 2, 3]
        }

        existing_df = pl.DataFrame(existing_df_data)
        new_df = pl.DataFrame(new_df_data)
        expected_df = pl.DataFrame(expected_df_data)

        result = self.writer._merge_dataframes(existing_df, new_df)

        assert_frame_equal(result, expected_df, check_column_order=False)

    def test_update_to_existing_column(self):
        """Test when values have changed for an existing timestamp and column"""
        existing_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_a": [1, 2, 3]
        }

        new_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_a": [4, 5, 6]
        }

        expected_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_a": [4, 5, 6]
        }

        existing_df = pl.DataFrame(existing_df_data)
        new_df = pl.DataFrame(new_df_data)
        expected_df = pl.DataFrame(expected_df_data)

        result = self.writer._merge_dataframes(existing_df, new_df)

        assert_frame_equal(result, expected_df)

    def test_update_to_existing_columns(self):
        """Test when values have changed for multiple timestamps and columns"""
        existing_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_a": [1, 2, 3],
            "col_b": [4, 5, 6],
            "col_c": [7, 8, 9],
            "col_d": [10, 11, 12]
        }

        new_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_a": [4, 5, 6],
            "col_d": [13, 14, 15]
        }

        expected_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_a": [4, 5, 6],
            "col_b": [4, 5, 6],
            "col_c": [7, 8, 9],
            "col_d": [13, 14, 15]
        }

        existing_df = pl.DataFrame(existing_df_data)
        new_df = pl.DataFrame(new_df_data)
        expected_df = pl.DataFrame(expected_df_data)

        result = self.writer._merge_dataframes(existing_df, new_df)

        assert_frame_equal(result, expected_df, check_column_order=False)

    def test_different_timestamps_no_overlap(self):
        """Test when the dataframes have completely different timestamps"""
        existing_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_a": [1, 2, 3]
        }

        new_df_data = {
            "time": [datetime(2023, 1, 1, 13, 0, 0), datetime(2023, 1, 1, 14, 0, 0), datetime(2023, 1, 1, 15, 0, 0)],
            "col_a": [4, 5, 6]
        }

        expected_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0),
                     datetime(2023, 1, 1, 13, 0, 0), datetime(2023, 1, 1, 14, 0, 0), datetime(2023, 1, 1, 15, 0, 0)],
            "col_a": [1, 2, 3, 4, 5, 6]
        }

        existing_df = pl.DataFrame(existing_df_data)
        new_df = pl.DataFrame(new_df_data)
        expected_df = pl.DataFrame(expected_df_data)

        result = self.writer._merge_dataframes(existing_df, new_df)

        assert_frame_equal(result.sort("time"), expected_df.sort("time"))

    def test_different_timestamps_overlap(self):
        """Test when there are some timestamps common to both dataframes."""
        existing_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_a": [1, 2, 3]
        }

        new_df_data = {
            "time": [datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0), datetime(2023, 1, 1, 13, 0, 0)],
            "col_a": [4, 5, 6]
        }

        expected_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0),
                     datetime(2023, 1, 1, 13, 0, 0)],
            "col_a": [1, 4, 5, 6]
        }

        existing_df = pl.DataFrame(existing_df_data)
        new_df = pl.DataFrame(new_df_data)
        expected_df = pl.DataFrame(expected_df_data)

        result = self.writer._merge_dataframes(existing_df, new_df)

        assert_frame_equal(result.sort("time"), expected_df.sort("time"))

    def test_different_timestamps_and_columns(self):
        """Test when there are a variety of timestamps and columns."""
        existing_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0)],
            "col_a": [1, 2, 3],
            "col_b": [4, 5, 6],
            "col_c": [7, 8, 9]
        }

        new_df_data = {
            "time": [datetime(2023, 1, 1, 12, 0, 0), datetime(2023, 1, 1, 13, 0, 0), datetime(2023, 1, 1, 14, 0, 0)],
            "col_a": [4, 5, 6]
        }

        expected_df_data = {
            "time": [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 11, 0, 0), datetime(2023, 1, 1, 12, 0, 0),
                     datetime(2023, 1, 1, 13, 0, 0), datetime(2023, 1, 1, 14, 0, 0)],
            "col_a": [1, 2, 4, 5, 6],
            "col_b": [4, 5, 6, None, None],
            "col_c": [7, 8, 9, None, None]
        }

        existing_df = pl.DataFrame(existing_df_data)
        new_df = pl.DataFrame(new_df_data)
        expected_df = pl.DataFrame(expected_df_data)

        result = self.writer._merge_dataframes(existing_df, new_df)

        assert_frame_equal(result.sort("time"), expected_df.sort("time"), check_column_order=False)

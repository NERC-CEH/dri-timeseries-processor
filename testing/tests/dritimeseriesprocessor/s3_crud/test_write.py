from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import moto
import polars as pl
from time_stream import TimeSeries
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.s3_crud.data_manager import query_by_date_range
from dritimeseriesprocessor.s3_crud.write import S3Writer
from dritimeseriesprocessor.utils import sterilize_dates
from testing.tests.dritimeseriesprocessor.s3_crud.base_test_case import BaseTestCase
from testing.utils.testing_helper import TestHelper


class TestS3Writer(BaseTestCase):
    """Test the s3 writer class"""

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


class TestS3WriterWithData(BaseTestCase):
    def setUp(self):

        start_date, end_date = sterilize_dates(date(2024, 1, 1), date(2024, 1, 4))

        self.data = query_by_date_range(
            bucket_name=self.bucket_name,
            prefix='cosmos/dataset=test_dataset',
            start_date=start_date,
            end_date=end_date,
            site_ids=['site1']
        )


    def test_polars_df_bytes_conversion(self):
        """Tests that a polars dataframe can be converted to bytes"""

        result = S3Writer._get_bytes(self.data)

        self.assertIsInstance(result, BytesIO)

        print(result.getvalue())

    def test_bytes_conversion_invalid_type_error(self):
        """Tests that an unsupported bytes conversion type raises and error"""

        with self.assertRaises(TypeError):
            S3Writer._get_bytes(47)

    @moto.mock_aws
    @patch("dritimeseriesprocessor.s3_crud.write.S3Writer._get_bytes", wraps=S3Writer._get_bytes)
    def test_bytes_conversion_called_if_not_bytes(self, mock_get_bytes):
        """Test that the _get_bytes() method is called if body to write passed
        is not a bytes object"""

        writer = S3Writer(self.s3_client)

        writer.write(
            bucket_name=self.bucket_name,
            resolution="test_resolution",
            network="test_network",
            site_id="site1",
            data=[(datetime(2024, 1, 9, 1, 1, 1), self.data)]
        )

        self.assertEqual(mock_get_bytes.called, 1)


    def test_group_data_by_resolution_and_site(self):
        """Test data correctly grouped by site and resolution."""
        input_filepath = Path(Path(__file__).parents[3], "data", "inputs", "write")
        output_filepath = Path(Path(__file__).parents[3], "data", "outputs", "write", "group_res_site")

        # Load test data into ts_ids structure
        # Test data consists of
        # - Data of the same site and resolution but with different columns and different times
        # (to test dataframes correctly merged)
        # - Data of the same resolution but different sites (to test they are correctly separated)
        test_helper = TestHelper()
        test_ts_ids = test_helper.load_ts_ids_from_json_file(input_filepath.joinpath("processed_ts_ids.json"))

        # For write methods we only need processed datasets and their metadata
        processed_timeseries = [
            metadata for metadata in test_ts_ids.values() if metadata["processing_level"] == "processed"]

        writer = S3Writer(self.s3_client)
        result = writer._group_data_by_resolution_and_site(processed_timeseries)

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
        input_filepath = Path(Path(__file__).parents[3], "data", "outputs", "write", "group_res_site")

        # Load test data
        # Just need to test on one dataframe with multiple dates
        test_timeseries = pl.read_parquet(input_filepath.joinpath("PT30M_ALIC1.parquet"))
        
        writer = S3Writer(self.s3_client)
        result = writer._split_by_date(test_timeseries)

        # Should be 2 dataframes
        assert len(result) == 2

        for date, data in result:
            expected = test_timeseries.filter((pl.col('time').dt.date() == date))
            assert_frame_equal(data, expected)

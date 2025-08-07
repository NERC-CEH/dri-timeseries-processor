from datetime import date, datetime
from io import BytesIO
from unittest.mock import patch

import moto
import polars as pl
import polars.testing

from dritimeseriesprocessor.s3_crud.data_manager import query_by_date_range
from dritimeseriesprocessor.s3_crud.read import DuckDbParquetReader
from dritimeseriesprocessor.s3_crud.write import S3Writer
from dritimeseriesprocessor.utils import sterilize_dates
from testing.tests.dritimeseriesprocessor.s3_crud.base_test_case import BaseTestCase


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


    def test_s3_key_builder(self, network='network', dataset='test', site_id='BUNNY', date=datetime(2024, 2, 22, 1, 32, 14)):
        """Tests that the _build_s3_key method returns correctly"""
        
        result = S3Writer._build_s3_key(network, dataset, site_id, date)
        expected = f'network={network}/dataset={dataset}/site={site_id}/date=2024-02-22/data.parquet'
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

    def test_objects_grouped_by_resolution():
        """"""
        pass

    def test_objects_split_by_day(self):
        """Test that df is split correctly."""

        writer = S3Writer(self.s3_client)

        result = writer._split_by_date(self.data)

        # Should be 4 dataframes
        assert len(result) == 4

        for date, data in result:
            expected = self.data.filter((pl.col('time').dt.date() == date))
            polars.testing.assert_frame_equal(data, expected)


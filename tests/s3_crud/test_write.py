from datetime import date
from io import BytesIO
from unittest.mock import patch

import moto
import polars.testing
from parameterized import parameterized

from tests.s3_crud.base_test_case import BaseTestCase
from dritimeseriesprocessor.s3_crud.write import S3Writer
from dritimeseriesprocessor.s3_crud.read import DuckDbParquetReader
from dritimeseriesprocessor.s3_crud.data_manager import query_by_date_range
from dritimeseriesprocessor.utils import steralize_dates


class TestS3Writer(BaseTestCase):
    def test_s3_client_type(self):
        """Returns an object if s3_client is of type `boto3.client.s3`, otherwise
        raises an error"""

        # Happy path
        writer = S3Writer(self.s3_client)

        # Bad path
        
        with self.assertRaises(TypeError):
            S3Writer("not an s3 client")

    @parameterized.expand([
        [date(2024, 2, 22), date(2024, 3, 1), "start_date=2024-02-22/end_date=2024-03-01/2024-02-22<=>2024-03-01"],
        [date(2001, 12, 9), date(4025, 3, 1), "start_date=2001-12-09/end_date=4025-03-01/2001-12-09<=>4025-03-01"],
        [date(1, 2, 6), date(2024, 3, 27), "start_date=1-02-06/end_date=2024-03-27/1-02-06<=>2024-03-27"],
    ])
    def test_date_range_key_builder(self, start_date, end_date, expected):
        """Tests that the _build_date_range_key method returns correctly"""
        
        result = S3Writer._build_date_range_partition_key(start_date, end_date)
        self.assertEqual(result, expected)


class TestS3WriterWithData(BaseTestCase):
    def setUp(self):
        start_date, end_date = steralize_dates(date(2024, 1, 1), date(2024, 1, 4))
        
        self.data = query_by_date_range(
            bucket_name=self.bucket_name,
            prefix='TEST_CATEGORY',
            start_date=start_date,
            end_date=end_date
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
            bucket_name=self.empty_bucket_name,
            key="test_path",
            body=self.data)

        self.assertEqual(mock_get_bytes.called, 1)
        
    def test_object_written(self):
        """Tests that the write() method writes to S3"""
        
        writer = S3Writer(self.s3_client)

        writer.write(
            bucket_name=self.empty_bucket_name,
            key="test_path.parquet",
            body=self.data)

        reader = DuckDbParquetReader()

        result = reader.read(
            query = f"SELECT * FROM read_parquet('s3://{self.empty_bucket_name}/test_path.parquet');"
        )

        polars.testing.assert_frame_equal(result, self.data)

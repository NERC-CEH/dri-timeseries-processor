import unittest
from unittest.mock import patch

import boto3
import moto
import polars as pl

from dritimeseriesprocessor.read_parquet import read_parquet_by_config


@moto.mock_aws
class TestGetParquetByDates(unittest.TestCase):
    def setUp(self):
        self.s3_client = boto3.client("s3")

        # Create a test bucket to store parquet files
        self.bucket_name = "test-bucket"
        self.s3_client.create_bucket(Bucket=self.bucket_name,
                                     CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})
        
        # Create a test empty bucket
        self.empty_bucket_name = "empty-bucket"
        self.s3_client.create_bucket(Bucket=self.empty_bucket_name,
                                     CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})

        # Add the test parquet files to the test bucket
        self.s3_client.upload_file(Filename='parquet-data/PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-17.parquet',
                                   Bucket=self.bucket_name,
                                   Key='PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-17.parquet')
        
        self.s3_client.upload_file(Filename='parquet-data/PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-18.parquet',
                                   Bucket=self.bucket_name,
                                   Key='PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-18.parquet')

        self.s3_client.upload_file(Filename='parquet-data/PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-19.parquet',
                                   Bucket=self.bucket_name,
                                   Key='PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-19.parquet')
        
        self.s3_client.upload_file(Filename='parquet-data/SOILMET_1MIN_2024_LOOPED/2024-01/2024-01-21.parquet',
                                   Bucket=self.bucket_name,
                                   Key='SOILMET_1MIN_2024_LOOPED/2024-01/2024-01-21.parquet')

        self.s3_client.upload_file(Filename='parquet-data/SOILMET_1MIN_2024_LOOPED/2024-01/2024-01-22.parquet',
                                   Bucket=self.bucket_name,
                                   Key='SOILMET_1MIN_2024_LOOPED/2024-01/2024-01-22.parquet')


    def test_read_parquet_files_one_date_range_one_type(self):
        """ Test that a Dataframe is returned containing all dates
        from requested date range where we know all dates exist. Done for 
        one data type.
        """
        filter_config = {
                            "datasets": [
                                {
                                "type": "PRECIP_1MIN_2024_LOOPED",
                                "range": ["2024-01-17", "2024-01-18"]
                                }
                            ]
                        }


        with patch('dritimeseriesprocessor.read_parquet.s3_client', self.s3_client):
            df = read_parquet_by_config(self.bucket_name, filter_config)
        print(df)
        # Convert datetime to string date for easy assertion
        df = df.with_columns(pl.col('time').dt.strftime('%Y-%m-%d'))
        unique_dates = df.select('time').unique()

        self.assertEqual(sorted(unique_dates['time'].to_list()), ['2024-01-17', '2024-01-18'])


    def test_read_parquet_files_two_date_ranges_one_type(self):
        """ Test that a Dataframe is returned containing all dates
        from requested date ranges where we know all dates exist. Done for 
        one data type.
        """
        filter_config = {
                            "datasets": [
                                {
                                "type": "PRECIP_1MIN_2024_LOOPED",
                                "range": ["2024-01-17", "2024-01-17"]
                                },
                                {
                                "type": "PRECIP_1MIN_2024_LOOPED",
                                "range": ["2024-01-19", "2024-01-19"]
                                }
                            ]
                        }


        with patch('dritimeseriesprocessor.read_parquet.s3_client', self.s3_client):
            df = read_parquet_by_config(self.bucket_name, filter_config)

        # Convert datetime to string date for easy assertion
        df = df.with_columns(pl.col('time').dt.strftime('%Y-%m-%d'))
        unique_dates = df.select('time').unique()

        self.assertEqual(sorted(unique_dates['time'].to_list()), ['2024-01-17', '2024-01-19'])


    def test_read_parquet_files_one_date_range_two_types(self):
        """ Test that a Dataframe is returned containing all dates
        from requested date ranges where we know all dates exist. Done for 
        two data types.
        """
        filter_config = {
                            "datasets": [
                                {
                                "type": "PRECIP_1MIN_2024_LOOPED",
                                "range": ["2024-01-17", "2024-01-17"]
                                },
                                {
                                "type": "SOILMET_1MIN_2024_LOOPED",
                                "range": ["2024-01-21", "2024-01-21"]
                                }
                            ]
                        }


        with patch('dritimeseriesprocessor.read_parquet.s3_client', self.s3_client):
            df = read_parquet_by_config(self.bucket_name, filter_config)

        # Convert datetime to string date for easy assertion
        df = df.with_columns(pl.col('time').dt.strftime('%Y-%m-%d'))
        unique_dates = df.select('time').unique()

        self.assertEqual(sorted(unique_dates['time'].to_list()), ['2024-01-17', '2024-01-21'])


    def test_read_parquet_files_one_type_filter_columns(self):
        """ Test that a Dataframe is returned with specified columns only."""
        filter_config = {
                            "datasets": [
                                {
                                "type": "PRECIP_1MIN_2024_LOOPED",
                                "range": ["2024-01-17", "2024-01-17"],
                                "columns": ["time", "SITE_ID", "P_HEATING_STATUS"]
                                }
                            ]
                        }


        with patch('dritimeseriesprocessor.read_parquet.s3_client', self.s3_client):
            df = read_parquet_by_config(self.bucket_name, filter_config)

        self.assertEqual(df.columns, ["time", "SITE_ID", "P_HEATING_STATUS"]) 


    def test_read_parquet_files_two_types_filter_columns(self):
        """ Test that a Dataframe is returned with columns spanning
        both dataset.
        """
        filter_config = {
                            "datasets": [
                                {
                                "type": "PRECIP_1MIN_2024_LOOPED",
                                "range": ["2024-01-17", "2024-01-17"],
                                "columns": ["time", "SITE_ID", "P_HEATING_STATUS"]
                                },
                                {
                                "type": "SOILMET_1MIN_2024_LOOPED",
                                "range": ["2024-01-20", "2024-01-21"],
                                "columns": ["time", "SITE_ID"]
                                }
                            ]
                        }


        with patch('dritimeseriesprocessor.read_parquet.s3_client', self.s3_client):
            df = read_parquet_by_config(self.bucket_name, filter_config)

        self.assertEqual(df.columns, ["time", "SITE_ID", "P_HEATING_STATUS"]) 

    
    def test_read_parquet_files_in_date_range_no_files(self):
        """ Test that an empty Dataframe is returned when requesting
        dates that all don't have any data.
        """
        filter_config = {
                            "datasets": [
                                {
                                "type": "SOILMET_1MIN_2024_LOOPED",
                                "range": ["2024-05-18", "2024-06-19"]
                                }
                            ]
                        }

        with patch('dritimeseriesprocessor.read_parquet.s3_client', self.s3_client):
            df = read_parquet_by_config(self.bucket_name, filter_config)

        self.assertTrue(df.is_empty())


    def test_corrupted_parquet_file(self):
        """ Test that an error is raised if a corrupted parquet file is found."""
        filter_config = {
                            "datasets": [
                                {
                                "type": "SOILMET_1MIN_2024_LOOPED",
                                "range": ["2024-01-11", "2024-01-15"]
                                }
                            ]
                        }

        self.s3_client.put_object(Bucket=self.bucket_name,
                                  Key='SOILMET_1MIN_2024_LOOPED/2024-01/2024-01-11.parquet',
                                  Body=b'corrupted data')

        with patch('dritimeseriesprocessor.read_parquet.s3_client', self.s3_client):
            with self.assertRaises(pl.exceptions.ComputeError):
                read_parquet_by_config(self.bucket_name, filter_config)


    def test_empty_bucket(self):
        """ Test that an empty bucket returns nothing."""
        filter_config = {
                            "datasets": [
                                {
                                "type": "SOILMET_1MIN_2024_LOOPED",
                                "range": ["2024-05-18", "2024-06-19"]
                                }
                            ]
                        }

        with patch('dritimeseriesprocessor.read_parquet.s3_client', self.s3_client):
            df = read_parquet_by_config(self.empty_bucket_name, filter_config)

        self.assertTrue(df.is_empty())

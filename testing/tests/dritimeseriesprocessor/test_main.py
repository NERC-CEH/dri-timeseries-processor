import logging
from io import BytesIO
from unittest import mock

import polars as pl

from dritimeseriesprocessor.__main__ import main
from metadata_manager.api_manager import MetadataAPIManager
from testing.utils.mock_metadata_api import MockMetadataAPI
from testing.utils.s3_test_helper import S3TestHelper

logger = logging.getLogger(__name__)


@mock.patch.object(MetadataAPIManager, "_make_api_call")
class TestMain(S3TestHelper):
    """End to end test of the timeseries processor.

    Run a CLI based test for the timeseries processor and compare the outputs against a series of expected parquet
    files.

    This is designed to test running the dritimeseriesprocessor end to end calling __main__.py from the command line
    as if it were being run by the user.

    It is assumed that the structure of the expected outputs will match the storage of the generated outputs on S3
    """

    def test_main_no_existing_processed_data(self, mock_api_manager: mock.MagicMock) -> None:
        """Test processing when no existing processed data exists"""

        expected_base_dir=self.output_dir.joinpath("end_to_end", "no_existing")
        output_bucket_name="ukceh-fdri-staging-timeseries-processed"
        cli_args=[
            "--sites", "alic1,bunny",
            "--columns", "PE,TA",
            "--periodicity", "PT30M,P1D",
            "--period", "P2D",
            "--network", "cosmos"
        ]

        # create mock api responses
        api_data = self.create_all_metadata_api_data()
        mock_api_manager.side_effect = MockMetadataAPI(api_data=api_data)

        # run the processor
        main(cli_args)

        # check the outputs
        self._check_expected_parquet_files_exist_in_bucket(expected_base_dir, output_bucket_name)


    def test_main_existing_processed_data(self, mock_api_manager: mock.MagicMock) -> None:
        """Test processing when existing processed data exists"""
        base_input_dir=self.input_dir.joinpath("end_to_end")
        expected_base_output_dir=self.output_dir.joinpath("end_to_end", "existing")
        output_bucket_name="ukceh-fdri-staging-timeseries-processed"
        cli_args=[
            "--sites", "alic1,bunny",
            "--columns", "PE,TA",
            "--periodicity", "PT30M,P1D",
            "--period", "P2D",
            "--network", "cosmos"
        ]

        # load some data into the bucket to mimic the update process when writing
        # - data for a column not in the test data (STP_TSOIL2) and one that is (TA)
        # - resolution PT30M
        # - no data for 2024-03-10
        # - no BUNNY data for 2024-03-08
        # - data between 4 and 7 for ALIC1 on 2024-03-09
        # - data between 14 and 19 for BUNNY on 2024-03-09
        keys = ["network=cosmos/date=2024-03-08/site=ALIC1/resolution=PT30M/data.parquet",
                "network=cosmos/date=2024-03-09/site=ALIC1/resolution=PT30M/data.parquet",
                "network=cosmos/date=2024-03-09/site=BUNNY/resolution=PT30M/data.parquet"]
        
        for key in keys:
            buffer = BytesIO()
            input_filepath = base_input_dir.joinpath(key)
            data = pl.read_parquet(input_filepath)
            data.write_parquet(buffer)
            buffer.seek(0)
            self.s3_client.put_object(Bucket=output_bucket_name, Key=key, Body=buffer.getvalue())


        # create mock api responses
        api_data = self.create_all_metadata_api_data()
        mock_api_manager.side_effect = MockMetadataAPI(api_data=api_data)

        # run the processor
        main(cli_args)

        # check the outputs
        self._check_expected_parquet_files_exist_in_bucket(expected_base_output_dir, output_bucket_name)

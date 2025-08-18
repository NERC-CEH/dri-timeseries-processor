import logging
import polars as pl
from io import BytesIO
from unittest import mock

from dritimeseriesprocessor.__main__ import main
from metadata_manager.api_manager import MetadataAPIManager
from testing.utils.s3_test_helper import S3TestHelper
from testing.utils.mock_metadata_api import MockMetadataAPI




logger = logging.getLogger(__name__)


@mock.patch.object(MetadataAPIManager, "_make_api_call")
class TestMain(S3TestHelper):
    def test_main_no_previous_data(self, mock_api_manager: mock.MagicMock) -> None:
        """End to end test of the timeseries processor.

        Run a CLI based test for the timeseries processor and compare the outputs against a series of expected parquet
        files.

        This is designed to test running the dritimeseriesprocessor end to end calling __main__.py from the command line
        as if it were being run by the user.

        It is assumed that the structure of the expected outputs will match the storage of the generated outputs on S3

        Args:
            cli_args: List of arguments to provide to the command line when running the test. Each component should be
                a single item in the list, for example ["--network", "cosmos", "--site", "alic1"] etc.
            expected_base_dir: Path to the base directory containing the expected data. This should be the equivalent
                of the output bucket used for generating the data during the test. It is assumed that all folders
                within this directory when combined match the structure of the s3 used to store the generated data.
                For example, `expected_base_directory/network/date/site/resolution/data.parquet`
            output_bucket_name: Name of the output bucket to store any data generated during the test. This will be
                cleared before the test starts.
        """
        expected_base_dir=self.output_dir.joinpath("end_to_end", "no_previous_data")
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

    def test_main_previous_data(self, mock_api_manager: mock.MagicMock) -> None:

        # load in, remove half the day, save out
        # load back then add extra column, overwrite a column and have a full day worth
        expected_base_dir=self.output_dir.joinpath("end_to_end", "previous_data")
        output_bucket_name="ukceh-fdri-staging-timeseries-processed"

        # create mock api responses
        api_data = self.create_all_metadata_api_data()
        mock_api_manager.side_effect = MockMetadataAPI(api_data=api_data)

        cli_args_first_run=[
            "--sites", "bunny",
            "--columns", "PA,TA",
            "--periodicity", "PT30M",
            "--period", "P0D",
            "--network", "cosmos"
        ]

        # run the processor
        main(cli_args_first_run)

        # remove half a days data from the outputs
        buffer = BytesIO()
        key = "network=cosmos/date=2024-03-10/site=BUNNY/resolution=PT30M/data.parquet"
        existing_data = self.s3_client.get_object(Bucket=output_bucket_name, Key=key)
        existing_df = pl.read_parquet(existing_data["Body"].read())

        existing_df = existing_df.head(n=24)
        existing_df.write_parquet(buffer)

        buffer.seek(0)
        self.s3_client.put_object(Bucket=output_bucket_name, Key=key, Body=buffer.getvalue())

        # remove some of the outputs

        # rerun with
        cli_args_second_run=[
            "--sites", "bunny",
            "--columns", "PA,TA",
            "--periodicity", "PT30M",
            "--period", "P1D",
            "--network", "cosmos"
        ]

        main(cli_args_second_run)
        self._check_expected_parquet_files_exist_in_bucket(expected_base_dir, output_bucket_name)
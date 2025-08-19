import logging
import polars as pl
import subprocess
from io import BytesIO
from unittest import mock

from dritimeseriesprocessor.__main__ import main
from metadata_manager.api_manager import MetadataAPIManager
from testing.utils.s3_test_helper import S3TestHelper
from testing.utils.mock_metadata_api import MockMetadataAPI


logger = logging.getLogger(__name__)


@mock.patch.object(MetadataAPIManager, "_make_api_call")
class TestMain(S3TestHelper):
    def test_main(self, mock_api_manager: mock.MagicMock) -> None:
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
        base_input_dir=self.input_dir.joinpath("end_to_end")
        expected_base_output_dir=self.output_dir.joinpath("end_to_end", "basic")
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
            input_filepath = base_input_dir.joinpath(key)
            subprocess.run(["awslocal", "s3api", "put-object", "--bucket", f"{output_bucket_name}",
                            "--key", f"{key}", "--body", f"{input_filepath}"])


        # create mock api responses
        api_data = self.create_all_metadata_api_data()
        mock_api_manager.side_effect = MockMetadataAPI(api_data=api_data)

        # run the processor
        main(cli_args)

        # check the outputs
        self._check_expected_parquet_files_exist_in_bucket(expected_base_output_dir, output_bucket_name)

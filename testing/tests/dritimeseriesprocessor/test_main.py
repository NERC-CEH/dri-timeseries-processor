import logging
import polars as pl
from unittest import mock

from dritimeseriesprocessor.__main__ import main
from metadata_manager.api_manager import MetadataAPIManager
from testing.utils.s3_test_helper import s3TestHelper
from testing.utils.mock_metadata_api import MockMetadataAPI

from polars.testing import assert_frame_equal


logger = logging.getLogger(__name__)


@mock.patch.object(MetadataAPIManager, "_make_api_call")
class TestMain(s3TestHelper):
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
        expected_base_dir=self.output_dir.joinpath("end_to_end", "basic")
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

        # Check that for every expected parquet file, the corresponding parquet has been generated with a matching
        # path structure (i.e. same s3 keys) and contents
        for expected_path in expected_base_dir.rglob("data.parquet"):
            expected_s3_key = str(expected_path.relative_to(expected_base_dir))
            actual_data = pl.read_parquet(self._get_s3_object(bucket_name=output_bucket_name, s3_key=expected_s3_key))
            expected_data = self._read_expected_data(s3_key=expected_s3_key, expected_base_dir=expected_base_dir)

            assert_frame_equal(actual_data, expected_data)

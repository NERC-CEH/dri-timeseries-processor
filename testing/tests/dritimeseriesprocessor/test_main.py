import logging
from unittest import mock

from metadata_manager.api_manager import MetadataAPIManager
from testing.utils.end_to_end_test_helper import EndToEndTestHelper
from testing.utils.mock_metadata_api import MockMetadataAPI

logger = logging.getLogger(__name__)


@mock.patch.object(MetadataAPIManager, "_make_api_call")
class TestMain(EndToEndTestHelper):
    def test_main(self, mock_api_manager: mock.MagicMock) -> None:
        """End to end test of the timeseries processor."""
        api_data = self.create_all_metadata_api_data()
        mock_api_manager.side_effect = MockMetadataAPI(api_data=api_data)

        self.run_cli_test(
            cli_args=[
                "--sites",
                "alic1,bunny",
                "--columns",
                "PE,TA",
                "--periodicity",
                "PT30M,P1D",
                "--period",
                "P2D",
                "--network",
                "cosmos",
            ],
            expected_base_dir=self.output_dir.joinpath("end_to_end", "basic"),
            output_bucket_name="ukceh-fdri-staging-timeseries-processed",
        )

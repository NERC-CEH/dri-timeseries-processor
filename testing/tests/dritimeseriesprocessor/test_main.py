import logging

from testing.utils.end_to_end_test_helper import EndToEndTestHelper

logger = logging.getLogger(__name__)


class TestMain(EndToEndTestHelper):
    def test_main(self) -> None:
        """End to end test of the timeseries processor."""

        self.run_cli_test(
            cli_args=[
                "--sites",
                "alic1",
                "--columns",
                "PE",
                "--periodicity",
                "PT30M",
                "--period",
                "P2D",
                "--network",
                "cosmos",
            ],
            expected_base_dir=self.output_dir.joinpath("end_to_end", "basic"),
            output_bucket_name="ukceh-fdri-staging-timeseries-processed",
        )

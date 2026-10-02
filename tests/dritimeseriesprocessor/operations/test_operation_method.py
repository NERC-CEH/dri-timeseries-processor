from datetime import datetime

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.operation_method import observation_interval


class TestObservationInterval:
    def test_no_start_date_means_no_interval(self) -> None:
        """Tests that a config without a start date gives no interval, so the method runs over all the data."""
        config = DataProcessingMethodConfig(method="test", params={})

        assert observation_interval(config) is None

    def test_start_date_only_leaves_the_end_open(self) -> None:
        """Tests that a config with only a start date gives an interval that runs to the end of the data."""
        config = DataProcessingMethodConfig(method="test", params={}, start_date=datetime(2025, 1, 1))

        assert observation_interval(config) == (datetime(2025, 1, 1), None)

    def test_start_and_end_dates_give_a_closed_interval(self) -> None:
        """Tests that a config with both dates gives them back as the interval to restrict the method to."""
        config = DataProcessingMethodConfig(
            method="test", params={}, start_date=datetime(2025, 1, 1), end_date=datetime(2025, 2, 1)
        )

        assert observation_interval(config) == (datetime(2025, 1, 1), datetime(2025, 2, 1))

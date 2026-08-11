import math
import time
from unittest.mock import patch

import pytest

from dritimeseriesprocessor.metrics.metrics import Metrics


@pytest.fixture
def metrics() -> Metrics:
    return Metrics("dummy-url", "test-job", site="site-a")


class TestMetrics:
    def test_histogram_time_records_duration(self, metrics: Metrics) -> None:
        """Test that histogram timing increases the recorded duration."""
        before = metrics.time_load._sum.get()
        wait_time = 0.1
        with metrics.time_load.time():
            time.sleep(wait_time)

        after = metrics.time_load._sum.get()
        assert math.isclose(after - before, wait_time, abs_tol=1e3)

    def test_counter_increments(self, metrics: Metrics) -> None:
        """Test that counters should increment correctly, per dataset label."""
        counter = metrics.success.labels(dataset="ds1")
        assert counter._value.get() == 0

        counter.inc()
        assert counter._value.get() == 1

        counter.inc(3)
        assert counter._value.get() == 4

        # A different dataset label tracks its own value.
        assert metrics.success.labels(dataset="ds2")._value.get() == 0

    def test_run_result_gauge(self, metrics: Metrics) -> None:
        """Test that the run_result gauge can be set to reflect overall run outcome."""
        metrics.run_result.set(1)
        assert metrics.run_result._value.get() == 1

        metrics.run_result.set(0)
        assert metrics.run_result._value.get() == 0

    def test_export_pushes_with_site_grouping_key(self, metrics: Metrics) -> None:
        """Test that exporting pushes the registry under the job name and a site grouping key."""
        with patch("dritimeseriesprocessor.metrics.metrics.push_to_gateway") as mock_push:
            metrics.export_metrics_to_pushgateway()

        mock_push.assert_called_once_with(
            gateway="dummy-url",
            job="test-job",
            registry=metrics.registry,
            grouping_key={"site": "site-a"},
        )

    def test_export_does_not_raise_when_push_fails(self, metrics: Metrics) -> None:
        """Test that a failure to reach the pushgateway is logged and swallowed rather than ending the run."""
        with patch("dritimeseriesprocessor.metrics.metrics.push_to_gateway", side_effect=OSError("gateway down")):
            metrics.export_metrics_to_pushgateway()

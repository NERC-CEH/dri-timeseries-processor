import math
import time

import pytest

from dritimeseriesprocessor.metrics.metrics import Metrics


@pytest.fixture
def metrics() -> Metrics:
    return Metrics("dummy-url", "test-job")


class TestMetrics:
    def test_histogram_time_records_duration(self, metrics: Metrics) -> None:
        """Test that histogram timing increases the recorded duration."""
        before = metrics.time_qc._sum.get()
        wait_time = 0.1
        with metrics.time_qc.time():
            time.sleep(wait_time)

        after = metrics.time_qc._sum.get()
        assert math.isclose(after - before, wait_time, abs_tol=1e3)

    def test_counter_increments(self, metrics: Metrics) -> None:
        """Test that counters should increment correctly."""
        assert metrics.success._value.get() == 0

        metrics.success.inc()
        assert metrics.success._value.get() == 1

        metrics.success.inc(3)
        assert metrics.success._value.get() == 4

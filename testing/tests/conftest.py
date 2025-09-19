import pytest

from testing.utils.base_test_helper import BaseTestHelper
from testing.utils.s3_test_helper import S3TestHelper
from testing.utils.timeseries_test_helper import TimeSeriesTestHelper


@pytest.fixture()
def base_test_helper() -> BaseTestHelper:
    base_test_helper = BaseTestHelper()

    yield base_test_helper

    base_test_helper.teardown()


@pytest.fixture()
def ts_test_helper() -> TimeSeriesTestHelper:
    ts_test_helper = TimeSeriesTestHelper()

    yield ts_test_helper

    ts_test_helper.teardown()


@pytest.fixture()
def s3_test_helper() -> S3TestHelper:
    s3_test_helper = S3TestHelper()

    yield s3_test_helper

    s3_test_helper.teardown()

from datetime import datetime
from unittest.mock import MagicMock

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from new_processor.routers.data.data_router import DuckDBDataRouter

TEST_DF = pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [10, 20]})


@pytest.fixture
def mock_reader() -> MagicMock:
    """Mock out DuckDBParquetReader so no backend is needed."""
    reader = MagicMock()
    reader.read.return_value = TEST_DF
    return reader


@pytest.fixture
def container() -> MagicMock:
    """Minimal TimeSeriesContainer fixture."""
    return MagicMock(
        source_bucket="a_bucket",
        source_dataset="a_dataset",
        network="a_network",
        source_site="a_network-a_site",
        source_column="a_column_name",
        source_site_identifier="A_SITE",
    )


@pytest.fixture
def router(mock_reader: MagicMock) -> DuckDBDataRouter:
    return DuckDBDataRouter(mock_reader)


class TestDuckDBDataRouter:
    def test_query_by_date_range(self, router: DuckDBDataRouter, mock_reader: MagicMock, container: MagicMock) -> None:
        start = datetime(2023, 1, 1)
        end = datetime(2023, 1, 2)

        expected_query = """
            SELECT time, a_column_name
            FROM read_parquet('s3://a_bucket/a_network/dataset=a_dataset/site=*/date=*/data.parquet')
            WHERE
                (date BETWEEN ? AND ?) AND
                site = ?;
        """

        result = router.query_by_date_range(container, start, end)
        call_query, call_params = mock_reader.read.call_args.args

        assert_frame_equal(result, TEST_DF)  # Return what the mock_reader returned
        assert call_query == expected_query
        assert call_params == [start, end, "A_SITE"]

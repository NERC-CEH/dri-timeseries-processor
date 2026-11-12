import io
from datetime import datetime
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock

import polars as pl
import pytest
from polars.testing import assert_frame_equal
from tests.utils.metadata_helpers import E2E_INPUT_BUCKET
from tests.utils.s3_test_helpers import get_s3_storage_client

from dritimeseriesprocessor.io_backend.duckdb_connection import create_duckdb_factory
from dritimeseriesprocessor.io_backend.reader import DuckDBParquetReader, RawFileReader
from dritimeseriesprocessor.routers.data.data_router import S3DataRouter
from dritimeseriesprocessor.storage.storage_client import S3StorageClient, StorageClient

TEST_DF = pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [10, 20]})
TEST_DATASET_PATH = "network=A_NETWORK/collection=a_data/site=A_SITE"
TEST_DATASET_URL = f"s3://a_bucket/{TEST_DATASET_PATH}"
LISTING_DATASET_URL = "s3://a_bucket/network=NET/collection=ds/site=S1"
FLUX_DATASET_URL = "s3://my-bucket/network=FDRI/collection=FLUX_20HZ/site=SITE1"


def day_url(day: str, dataset_url: str = LISTING_DATASET_URL, file_name: str = "data.parquet") -> str:
    """Build the URL of one day's file under a dataset's access URL."""
    return f"{dataset_url}/date={day}/{file_name}"


def fake_storage(urls: list[str]) -> MagicMock:
    """Build a mock storage client whose `list_urls` answers from `urls` the same way S3 does."""
    sorted_urls = sorted(urls)

    def list_urls(prefix_url: str) -> list[str]:
        return [url for url in sorted_urls if url.startswith(prefix_url)]

    storage = MagicMock(spec=StorageClient)
    storage.list_urls.side_effect = list_urls
    return storage


def router_with_urls(urls: list[str]) -> S3DataRouter:
    """Build a router whose storage holds `urls`, with the readers mocked out."""
    return S3DataRouter(MagicMock(), MagicMock(spec=RawFileReader), fake_storage(urls))


def make_container(
    source_column: str = "a_column_name",
    access_url: str | None = TEST_DATASET_URL,
    time_column_name: str = "a_time",
    ts_id: str = "ds-1",
) -> MagicMock:
    """Build a mock container with just the attributes the router reads."""
    return MagicMock(
        ts_id=ts_id,
        access_url=access_url,
        source_column=source_column,
        source_site_identifier="A_SITE",
        time_column_name=time_column_name,
    )


@pytest.fixture
def mock_reader() -> MagicMock:
    """Mock out DuckDBParquetReader so no backend is needed."""
    reader = MagicMock()
    reader.read.return_value = TEST_DF
    return reader


@pytest.fixture
def mock_raw_reader() -> MagicMock:
    return MagicMock(spec=RawFileReader)


@pytest.fixture
def mock_storage() -> MagicMock:
    """Storage holding two days of files for the `A_SITE` test containers."""
    return fake_storage([day_url("2023-01-01", TEST_DATASET_URL), day_url("2023-01-02", TEST_DATASET_URL)])


@pytest.fixture
def router(mock_reader: MagicMock, mock_raw_reader: MagicMock, mock_storage: MagicMock) -> S3DataRouter:
    return S3DataRouter(mock_reader, mock_raw_reader, mock_storage)


@pytest.fixture(scope="module")
def s3_storage_client() -> Iterator[S3StorageClient]:
    with get_s3_storage_client() as storage_client:
        yield storage_client


class TestS3DataRouter:
    def test_query_by_date_range(self, router: S3DataRouter, mock_reader: MagicMock) -> None:
        """Tests that the query reads the listed file URLs for the date range, matching their columns by name."""
        expected_query = """
            SELECT a_time, COLUMNS(c -> c IN ('a_column_name'))
            FROM read_parquet(?, union_by_name=true);
        """

        result = router.query_by_date_range(
            make_container(), start_date=datetime(2023, 1, 1), end_date=datetime(2023, 1, 2)
        )
        call_query, call_params = mock_reader.read.call_args.args

        assert_frame_equal(result, TEST_DF)  # Return what the mock_reader returned
        assert " ".join(call_query.split()) == " ".join(expected_query.split())  # Collapse the whitespace for compare
        assert call_params == [[day_url("2023-01-01", TEST_DATASET_URL), day_url("2023-01-02", TEST_DATASET_URL)]]

    def test_query_returns_empty_frame_without_reading_when_no_files_found(self, mock_reader: MagicMock) -> None:
        """Tests that an empty frame is returned, and DuckDB isn't queried, when no files are in the date range."""
        router = S3DataRouter(mock_reader, MagicMock(spec=RawFileReader), fake_storage([]))

        result = router.query_by_date_range(
            make_container(), start_date=datetime(2023, 1, 1), end_date=datetime(2023, 1, 2)
        )

        assert result.is_empty()
        mock_reader.read.assert_not_called()

    def test_query_raises_when_no_access_url(self, router: S3DataRouter, mock_reader: MagicMock) -> None:
        """Tests that a container with no access URL fails the query rather than reading from a guessed location."""
        container = make_container(access_url=None)

        with pytest.raises(ValueError, match="No access URL"):
            router.query_by_date_range(container, start_date=datetime(2023, 1, 1), end_date=datetime(2023, 1, 2))
        mock_reader.read.assert_not_called()

    def test_query_raises_when_containers_have_different_access_urls(
        self, router: S3DataRouter, mock_reader: MagicMock
    ) -> None:
        """Tests that containers stored in different places can't be read together in one query."""
        container_1 = make_container(source_column="col_one")
        container_2 = make_container(source_column="col_two", access_url=LISTING_DATASET_URL)

        with pytest.raises(ValueError, match="access_url"):
            router.query_by_date_range(
                container_1, container_2, start_date=datetime(2023, 1, 1), end_date=datetime(2023, 1, 2)
            )
        mock_reader.read.assert_not_called()

    def test_query_raises_when_containers_have_different_time_columns(
        self, router: S3DataRouter, mock_reader: MagicMock
    ) -> None:
        """Tests that containers with different time column names can't be read together in one query."""
        container_1 = make_container(source_column="col_one", time_column_name="time")
        container_2 = make_container(source_column="col_two", time_column_name="other_time")

        with pytest.raises(ValueError, match="time_column_name"):
            router.query_by_date_range(
                container_1, container_2, start_date=datetime(2023, 1, 1), end_date=datetime(2023, 1, 2)
            )
        mock_reader.read.assert_not_called()

    def test_query_by_date_range_builds_columns_lambda_for_multiple_containers(
        self, router: S3DataRouter, mock_reader: MagicMock
    ) -> None:
        """Tests that every container's source column is included in the COLUMNS(...) predicate."""
        container_1 = make_container(source_column="col_one")
        container_2 = make_container(source_column="col_two")

        router.query_by_date_range(
            container_1, container_2, start_date=datetime(2023, 1, 1), end_date=datetime(2023, 1, 2)
        )
        call_query, _ = mock_reader.read.call_args.args

        assert "COLUMNS(c -> c IN ('col_one', 'col_two'))" in call_query

    def test_read_from_partitioned_directory(self, s3_storage_client: S3StorageClient) -> None:
        """Tests reading the files under a dataset's access URL"""
        router = S3DataRouter(DuckDBParquetReader(create_duckdb_factory()), MagicMock(), s3_storage_client)
        container = make_container(
            source_column="value",
            access_url=f"s3://{E2E_INPUT_BUCKET}/{TEST_DATASET_PATH}",
            time_column_name="time",
        )

        expected = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1), datetime(2023, 1, 1, 1), datetime(2023, 1, 1, 2)],
                "value": [1.23, 45.6, 7.89],
            }
        )

        result = router.query_by_date_range(container, start_date=datetime(2023, 1, 1), end_date=datetime(2023, 1, 1))

        assert_frame_equal(result, expected)

    def test_missing_column_is_dropped_without_failing_other_containers(
        self, s3_storage_client: S3StorageClient
    ) -> None:
        """Tests that a source_column not present in the parquet files is silently omitted from the result,
        rather than raising and losing every other container queried in the same group.
        """
        router = S3DataRouter(DuckDBParquetReader(create_duckdb_factory()), MagicMock(), s3_storage_client)
        dataset_url = f"s3://{E2E_INPUT_BUCKET}/{TEST_DATASET_PATH}"
        existing_column_container = make_container("value", dataset_url, "time")
        missing_column_container = make_container("does_not_exist", dataset_url, "time")

        result = router.query_by_date_range(
            existing_column_container,
            missing_column_container,
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 1),
        )

        assert "value" in result.columns
        assert "does_not_exist" not in result.columns
        assert not result.is_empty()

    @pytest.mark.parametrize(
        ("site_identifier", "first_file", "second_file", "expected_extra_column"),
        [
            pytest.param(
                "ADDED_SITE",
                pl.DataFrame({"time": [datetime(2023, 1, 1)], "value": [1.0]}),
                pl.DataFrame({"time": [datetime(2023, 1, 2)], "value": [2.0], "extra_column": [3.0]}),
                [None, 3.0],
                id="column_added_in_second_file",
            ),
            pytest.param(
                "REMOVED_SITE",
                pl.DataFrame({"time": [datetime(2023, 1, 1)], "value": [1.0], "extra_column": [3.0]}),
                pl.DataFrame({"time": [datetime(2023, 1, 2)], "value": [2.0]}),
                [3.0, None],
                id="column_missing_from_second_file",
            ),
        ],
    )
    def test_reads_files_with_differing_schemas_in_one_query(
        self,
        site_identifier: str,
        first_file: pl.DataFrame,
        second_file: pl.DataFrame,
        expected_extra_column: list[float | None],
        s3_storage_client: S3StorageClient,
    ) -> None:
        """Tests that both dates are read by a single query when their parquet files hold different columns.

        DuckDB takes the schema from the first file it reads, so a column that only one of the files has fails
        the whole read unless the query unions the files by name.
        """
        dataset_url = (
            f"s3://{E2E_INPUT_BUCKET}/network=EVOLVING_NETWORK/collection=evolving_data/site={site_identifier}"
        )

        for date, frame in [("2023-01-01", first_file), ("2023-01-02", second_file)]:
            buffer = io.BytesIO()
            frame.write_parquet(buffer)
            s3_storage_client.put_bytes(day_url(date, dataset_url), buffer.getvalue())

        router = S3DataRouter(DuckDBParquetReader(create_duckdb_factory()), MagicMock(), s3_storage_client)
        containers = [make_container(column, dataset_url, "time") for column in ("value", "extra_column")]

        result = router.query_by_date_range(*containers, start_date=datetime(2023, 1, 1), end_date=datetime(2023, 1, 2))

        expected = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
                "value": [1.0, 2.0],
                "extra_column": expected_extra_column,
            }
        )
        assert_frame_equal(result, expected)


class TestListFiles:
    def test_lists_days_in_range(self) -> None:
        """Tests that only the files for days inside the date range are listed, as full URLs."""
        days = ["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05"]
        router = router_with_urls([day_url(day) for day in days])

        result = router._list_files(LISTING_DATASET_URL, datetime(2023, 1, 2), datetime(2023, 1, 4))

        assert result == [day_url(day) for day in ["2023-01-02", "2023-01-03", "2023-01-04"]]

    def test_lists_each_month_separately_when_range_crosses_a_year(self) -> None:
        """Tests that a range crossing a year end lists each month on its own, not every year in between."""
        storage = fake_storage(
            [day_url("2022-12-30"), day_url("2022-12-31"), day_url("2023-01-01"), day_url("2023-01-02")]
        )
        router = S3DataRouter(MagicMock(), MagicMock(spec=RawFileReader), storage)

        result = router._list_files(LISTING_DATASET_URL, datetime(2022, 12, 31), datetime(2023, 1, 1))

        listed_prefixes = [call.args[0] for call in storage.list_urls.call_args_list]
        assert listed_prefixes == [f"{LISTING_DATASET_URL}/date=2022-12", f"{LISTING_DATASET_URL}/date=2023-01"]
        assert result == [day_url(day) for day in ["2022-12-31", "2023-01-01"]]

    def test_includes_start_and_end_days_whatever_the_time_of_day(self) -> None:
        """Tests that the whole of the start and end days are included when the dates have a time of day."""
        router = router_with_urls([day_url("2023-01-01"), day_url("2023-01-02"), day_url("2023-01-03")])

        result = router._list_files(LISTING_DATASET_URL, datetime(2023, 1, 2, 12), datetime(2023, 1, 3, 6))

        assert result == [day_url(day) for day in ["2023-01-02", "2023-01-03"]]

    def test_ignores_files_that_are_not_data_parquet(self) -> None:
        """Tests that other files in a day's folder are not listed."""
        router = router_with_urls([day_url("2023-01-01"), day_url("2023-01-01", file_name="notes.csv")])

        result = router._list_files(LISTING_DATASET_URL, datetime(2023, 1, 1), datetime(2023, 1, 1))

        assert result == [day_url("2023-01-01")]

    def test_ignores_files_in_folders_below_the_access_url(self) -> None:
        """Tests that files one folder further down (e.g. an old `serial_no=` folder) are not listed."""
        router = router_with_urls([day_url("2023-01-01", f"{LISTING_DATASET_URL}/serial_no=1234")])

        result = router._list_files(LISTING_DATASET_URL, datetime(2023, 1, 1), datetime(2023, 1, 1))

        assert result == []

    def test_returns_empty_list_when_dataset_has_no_files(self) -> None:
        """Tests that a dataset with no files gives an empty list."""
        router = router_with_urls([day_url("2023-01-01", "s3://a_bucket/network=NET/collection=ds/site=OTHER")])

        result = router._list_files(LISTING_DATASET_URL, datetime(2023, 1, 1), datetime(2023, 1, 1))

        assert result == []


class TestStageLocally:
    def test_calls_download_once_per_day_in_range(self, router: S3DataRouter, mock_raw_reader: MagicMock) -> None:
        """Tests that download is called once for each day in the date range, inclusive."""
        mock_raw_reader.download.return_value = []

        router.stage_locally(
            make_container(access_url=FLUX_DATASET_URL),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 3),
        )

        assert mock_raw_reader.download.call_count == 3

    def test_single_day_range_calls_download_once(self, router: S3DataRouter, mock_raw_reader: MagicMock) -> None:
        """Tests that a single-day range (start == end) results in exactly one download call."""
        mock_raw_reader.download.return_value = []

        router.stage_locally(
            make_container(access_url=FLUX_DATASET_URL),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 1),
        )

        assert mock_raw_reader.download.call_count == 1

    def test_builds_correct_date_prefix_per_day(self, router: S3DataRouter, mock_raw_reader: MagicMock) -> None:
        """Tests that each download call uses the day's folder under the access URL."""
        mock_raw_reader.download.return_value = []

        router.stage_locally(
            make_container(access_url=FLUX_DATASET_URL),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
        )

        call_prefixes = [call.args[0] for call in mock_raw_reader.download.call_args_list]
        assert call_prefixes == [f"{FLUX_DATASET_URL}/date=2024-01-01/", f"{FLUX_DATASET_URL}/date=2024-01-02/"]

    def test_raises_when_no_access_url(self, router: S3DataRouter, mock_raw_reader: MagicMock) -> None:
        """Tests that staging a dataset with no access URL fails before anything is downloaded."""
        with pytest.raises(ValueError, match="No access URL"):
            router.stage_locally(
                make_container(access_url=None), start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 1)
            )

        mock_raw_reader.download.assert_not_called()
        assert router._staged == []

    def test_returns_path_to_existing_local_directory(self, router: S3DataRouter, mock_raw_reader: MagicMock) -> None:
        """Tests that the returned path is a real directory that exists on disk."""
        mock_raw_reader.download.return_value = []

        result = router.stage_locally(
            make_container(access_url=FLUX_DATASET_URL),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 1),
        )

        assert isinstance(result, Path)
        assert result.is_dir()

    def test_staged_directory_is_tracked_for_cleanup(self, router: S3DataRouter, mock_raw_reader: MagicMock) -> None:
        """Tests that the temp directory is added to the staged list so cleanup can remove it."""
        mock_raw_reader.download.return_value = []

        router.stage_locally(
            make_container(access_url=FLUX_DATASET_URL),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 1),
        )

        assert len(router._staged) == 1


class TestCleanup:
    def test_cleanup_calls_cleanup_on_each_staged_dir(self, router: S3DataRouter) -> None:
        """Tests that cleanup is called on each tracked temp directory."""
        tmp1 = MagicMock()
        tmp2 = MagicMock()
        router._staged = [tmp1, tmp2]

        router.cleanup()

        tmp1.cleanup.assert_called_once()
        tmp2.cleanup.assert_called_once()

    def test_cleanup_closes_the_reader_connection(self, router: S3DataRouter, mock_reader: MagicMock) -> None:
        """Tests that cleanup closes the parquet reader's DuckDB connection."""
        router.cleanup()

        mock_reader.close.assert_called_once()

    def test_cleanup_empties_staged_list(self, router: S3DataRouter) -> None:
        """Tests that the staged list is empty after cleanup."""
        router._staged = [MagicMock(), MagicMock()]

        router.cleanup()

        assert router._staged == []

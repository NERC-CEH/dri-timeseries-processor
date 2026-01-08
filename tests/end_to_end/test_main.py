"""
Module to run end-to-end (E2E) tests for the time series processor.

These tests are intended to run the processor as a user would, but substituting external dependencies with local
versions:

- **Metadata API** is replaced by a mock HTTP server (``MockMetadataApi``) - injected via the `metadata_api_url`
  environment variable. This uses the cached metadata response JSONs as recorded by the `record_metadata.py` script.
- **S3 storage** is provided by LocalStack (via ``S3StorageClient``), with isolated input and output buckets created
  per test run.

Test cases are discovered from `test_cases.json` - this is so that the `record_metadata.py` script can also have
knowledge of which test cases are being considered and what metadata is required.

The processor is initialised and executed end-to-end with known input data, and the resulting outputs in the
are compared against known/expected Parquet files.
"""

import socket
import threading
from datetime import datetime, timedelta
from http.server import HTTPServer
from typing import Iterator

import polars as pl
import pytest
from polars.testing import assert_frame_equal
from tests.end_to_end.mock_metadata_api.mock_api import MockMetadataApi
from tests.utils.fixture_helpers import TEST_DATA_INPUT_DIR, TEST_DATA_OUTPUT_DIR, discover_e2e_test_cases
from tests.utils.metadata_helpers import E2E_INPUT_BUCKET, E2E_OUTPUT_BUCKET
from tests.utils.s3_test_helpers import create_test_s3_bucket, remove_test_s3_bucket, upload_folder_to_s3

from new_processor.__main__ import main
from new_processor.configuration.app_config import app_config
from new_processor.operations.flags.flag_names import (
    core_flag_column_name,
    corrs_flag_column_name,
    infill_flag_column_name,
    qc_flag_column_name,
)
from new_processor.storage.storage_client import S3StorageClient

CONFIG = app_config()


@pytest.fixture
def metadata_api_url() -> Iterator[str]:
    """Start a local mock metadata API server and yield its base URL.

    Yields:
        The base URL of the running mock metadata API.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    server = HTTPServer(("127.0.0.1", port), MockMetadataApi)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    metadata_api_base_url = f"http://127.0.0.1:{port}"

    try:
        yield metadata_api_base_url
    finally:
        server.shutdown()


@pytest.fixture
def s3_storage_client() -> Iterator[S3StorageClient]:
    """Set up the LocalStack storage client, creating test S3 buckets and upload the known input parquet data files."""
    storage_client = S3StorageClient("test", "test", CONFIG.AWS_DEFAULT_REGION, endpoint_url=CONFIG.endpoint_url)

    try:
        # Clean up in case of prior interrupted runs.
        remove_test_s3_bucket(E2E_INPUT_BUCKET, storage_client)
        remove_test_s3_bucket(E2E_OUTPUT_BUCKET, storage_client)
    except Exception:
        pass

    create_test_s3_bucket(E2E_INPUT_BUCKET, storage_client, CONFIG.AWS_DEFAULT_REGION)
    create_test_s3_bucket(E2E_OUTPUT_BUCKET, storage_client, CONFIG.AWS_DEFAULT_REGION)

    upload_folder_to_s3(storage_client, E2E_INPUT_BUCKET, TEST_DATA_INPUT_DIR / "end_to_end")

    try:
        yield storage_client
    finally:
        # teardown
        remove_test_s3_bucket(E2E_INPUT_BUCKET, storage_client)
        remove_test_s3_bucket(E2E_OUTPUT_BUCKET, storage_client)


class TestMain:
    """End-to-end tests of the timeseries processor."""

    @pytest.mark.parametrize(
        "network, sites, measured_variables, derived_variables, aggregated_variables, periodicities, start_date, "
        "end_date",
        discover_e2e_test_cases(),
    )
    def test_end_to_end(
        self,
        network: str,
        sites: list[str],
        measured_variables: list[str],
        derived_variables: list[str],
        aggregated_variables: list[str],
        periodicities: list[str],
        start_date: str,
        end_date: str,
        monkeypatch: pytest.MonkeyPatch,
        s3_storage_client: S3StorageClient,
        metadata_api_url: str,
    ) -> None:
        """Test that the processor can run end-to-end and compare output with known output."""
        monkeypatch.setenv("metadata_api_url", metadata_api_url)

        all_variables = measured_variables + derived_variables + aggregated_variables

        cli_args = [
            "from-cross-product",
            "--sites",
            *sites,
            "--variables",
            *all_variables,
            "--periodicities",
            *periodicities,
            "--network",
            network,
            "--start-date",
            start_date,
            "--end-date",
            end_date,
        ]

        # run the processor
        main(cli_args)

        # check the outputs
        expected_output_dir = TEST_DATA_OUTPUT_DIR / "end_to_end"

        # Build list of expected flag columns to validate alongside data variables.
        flag_cols = []
        for var in all_variables:
            flag_cols.append(core_flag_column_name(var))

        for var in measured_variables:
            flag_cols.append(corrs_flag_column_name(var))
            flag_cols.append(infill_flag_column_name(var))
            flag_cols.append(qc_flag_column_name(var))

        check_cols = all_variables + flag_cols + ["time"]

        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        date_range = [start_dt + timedelta(days=i) for i in range((end_dt - start_dt).days + 1)]

        for date in date_range:
            for site in sites:
                for resolution in periodicities:
                    expected_path = (
                        expected_output_dir
                        / f"network={network}/date={date}/site={site}/resolution={resolution}/data.parquet"
                    )
                    expected_s3_key = str(expected_path.relative_to(expected_output_dir))
                    result = pl.read_parquet(s3_storage_client.get_bytes(E2E_OUTPUT_BUCKET, expected_s3_key))
                    expected = pl.read_parquet(expected_path)

                    assert_frame_equal(result[check_cols], expected[check_cols])

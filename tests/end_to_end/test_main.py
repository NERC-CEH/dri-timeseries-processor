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

from datetime import datetime, timedelta
from typing import Iterator

import polars as pl
import pytest
from polars.testing import assert_frame_equal
from tests.end_to_end.mock_metadata_api.mock_api import mock_metadata_api
from tests.utils.eddypro_test_helpers import eddypro_mock_init, eddypro_mock_run
from tests.utils.fixture_helpers import TEST_DATA_OUTPUT_DIR, discover_e2e_test_cases
from tests.utils.metadata_helpers import E2E_OUTPUT_BUCKET
from tests.utils.s3_test_helpers import get_s3_storage_client

from dritimeseriesprocessor.__main__ import main
from dritimeseriesprocessor.operations.eddypro.eddypro_runner import EddyProRunner
from dritimeseriesprocessor.operations.flags.flag_names import (
    core_flag_column_name,
    corrs_flag_column_name,
    infill_flag_column_name,
    qc_flag_column_name,
)
from dritimeseriesprocessor.storage.storage_client import S3StorageClient


@pytest.fixture
def metadata_api_url() -> Iterator[str]:
    """Start a local mock metadata API server and yield its base URL.

    Yields:
        The base URL of the running mock metadata API.
    """
    with mock_metadata_api() as url:
        yield url


@pytest.fixture
def s3_storage_client() -> Iterator[S3StorageClient]:
    with get_s3_storage_client() as storage_client:
        yield storage_client


@pytest.fixture
def eddypro_runner_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace EddyProRunner with a no-op mock that returns pre-recorded output.

    Applied unconditionally — cosmos tests never call EddyProRunner so it is harmless.
    """
    monkeypatch.setattr(EddyProRunner, "__init__", eddypro_mock_init)
    monkeypatch.setattr(EddyProRunner, "run", eddypro_mock_run)


class TestMain:
    """End-to-end tests of the timeseries processor."""

    @pytest.mark.parametrize(
        "network, sites, measured_variables, derived_variables, aggregated_variables, periodicities, start_date, "
        "end_date, check_variables",
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
        check_variables: list[str] | None,
        monkeypatch: pytest.MonkeyPatch,
        s3_storage_client: S3StorageClient,
        metadata_api_url: str,
        eddypro_runner_mock: None,
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

        # Define time column name for different networks
        if network == "nmdb":
            time_col = ["timestamp"]
        else:
            time_col = ["time"]

        # Flux/EddyPro datasets encode quality as integer data columns (qc_H, qc_Tau) rather
        # than the standard FDRI _CORE/_QC/_CORRS/_INFILL flag scheme, so the auto-derived
        # flag column list would look for columns that don't exist. check_variables overrides it.
        if check_variables is not None:
            check_cols = check_variables + time_col
        else:
            # Build list of expected flag columns to validate alongside data variables.
            flag_cols = []
            for var in all_variables:
                flag_cols.append(core_flag_column_name(var))
            for var in measured_variables:
                flag_cols.append(corrs_flag_column_name(var))
                flag_cols.append(infill_flag_column_name(var))
                flag_cols.append(qc_flag_column_name(var))
            check_cols = all_variables + flag_cols + time_col

        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        date_range = [start_dt + timedelta(days=i) for i in range((end_dt - start_dt).days + 1)]

        for date in date_range:
            for site in sites:
                s3_site_id = site.split("-")[1].upper()
                for resolution in periodicities:
                    expected_path = (
                        expected_output_dir
                        / f"{network}/resolution={resolution}/site={s3_site_id}/date={date}/data.parquet"
                    )
                    expected_s3_key = str(expected_path.relative_to(expected_output_dir))
                    result = pl.read_parquet(s3_storage_client.get_bytes(E2E_OUTPUT_BUCKET, expected_s3_key))
                    expected = pl.read_parquet(expected_path)

                    assert_frame_equal(result[check_cols], expected[check_cols])

from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator
import threading
import socket
from http.server import HTTPServer

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from new_processor.__main__ import main
from new_processor.configuration.app_config import app_config
from new_processor.storage.storage_client import S3StorageClient
from utils.fixture_helpers import TEST_DATA_INPUT_DIR, TEST_DATA_OUTPUT_DIR, discover_e2e_test_cases
from tests.end_to_end.mock_metadata_api.mock_api import MockMetadataApi
from tests.utils.metadata_helpers import E2E_INPUT_BUCKET, E2E_OUTPUT_BUCKET
from new_processor.operations.flags.flag_names import corrs_flag_column_name, core_flag_column_name, qc_flag_column_name, infill_flag_column_name

CONFIG = app_config()


@pytest.fixture
def metadata_api_url(monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    server = HTTPServer(("127.0.0.1", port), MockMetadataApi)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    metadata_api_base_url = f"http://127.0.0.1:{port}"

    yield metadata_api_base_url

    server.shutdown()


@pytest.fixture
def s3_storage_client() -> Iterator[S3StorageClient]:
    # setup
    storage_client = S3StorageClient("test", "test", CONFIG.AWS_DEFAULT_REGION, endpoint_url=CONFIG.endpoint_url)

    try:
        remove_test_s3_bucket(E2E_INPUT_BUCKET, storage_client)
        remove_test_s3_bucket(E2E_OUTPUT_BUCKET, storage_client)
    except:
        pass

    create_test_s3_bucket(E2E_INPUT_BUCKET, storage_client)
    create_test_s3_bucket(E2E_OUTPUT_BUCKET, storage_client)

    upload_folder_to_s3(storage_client, E2E_INPUT_BUCKET, TEST_DATA_INPUT_DIR / "end_to_end")

    yield storage_client

    # teardown
    remove_test_s3_bucket(E2E_INPUT_BUCKET, storage_client)
    remove_test_s3_bucket(E2E_OUTPUT_BUCKET, storage_client)


def remove_test_s3_bucket(bucket, storage_client):
    storage_client.clear_bucket(bucket)
    storage_client.client.delete_bucket(Bucket=bucket)


def create_test_s3_bucket(bucket, storage_client):
    storage_client.client.create_bucket(
        Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": CONFIG.AWS_DEFAULT_REGION}
    )


def upload_folder_to_s3(storage_client, bucket, folder: Path) -> None:
    for file in folder.rglob("*.parquet"):
        key = str(file.relative_to(folder))
        storage_client.put_bytes(bucket, key, file.read_bytes())


class TestMain:
    """End-to-end test of the timeseries processor.

    Run a CLI based test for the timeseries processor and compare the outputs against a series of expected parquet
    files.

    This is designed to test running the processor end to end calling __main__.py from the command line
    as if it were being run by the user.

    It is assumed that the structure of the expected outputs will match the storage of the generated outputs on S3
    """

    @pytest.mark.parametrize(
        "network, sites, measured_variables, derived_variables, aggregated_variables, periodicities, start_date, end_date",
        discover_e2e_test_cases()
    )
    def test_end_to_end(
            self,
            network,
            sites,
            measured_variables,
            derived_variables,
            aggregated_variables,
            periodicities,
            start_date,
            end_date,
            monkeypatch,
            s3_storage_client,
            metadata_api_url
    ) -> None:
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
        pass

        # check the outputs
        expected_output_dir = TEST_DATA_OUTPUT_DIR / "end_to_end"

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
                    expected_path = expected_output_dir / f"network={network}/date={date}/site={site}/resolution={resolution}/data.parquet"

                    expected_s3_key = str(expected_path.relative_to(expected_output_dir))
                    result = pl.read_parquet(s3_storage_client.get_bytes(E2E_OUTPUT_BUCKET, expected_s3_key))

                    expected_path.parent.mkdir(parents=True, exist_ok=True)
                    result.write_parquet(expected_path)

                    expected = pl.read_parquet(expected_path)

                    assert_frame_equal(result[check_cols], expected[check_cols])

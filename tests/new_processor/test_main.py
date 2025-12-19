from pathlib import Path
from typing import Iterator

import polars as pl
import pytest
import requests
from polars.testing import assert_frame_equal

import new_processor
from new_processor.__main__ import main
from new_processor.configuration.app_config import app_config
from new_processor.storage.storage_client import S3StorageClient
from utils.fixture_helpers import TEST_DATA_INPUT_DIR, TEST_DATA_OUTPUT_DIR
from utils.metadata_helpers import all_metadata_api_data

CONFIG = app_config()

INPUT_BUCKET = "ukceh-fdri-staging-timeseries-level-0"
OUTPUT_BUCKET = "ukceh-fdri-staging-timeseries-processed"


@pytest.fixture
def storage_client() -> Iterator[S3StorageClient]:
    # setup
    buckets = [INPUT_BUCKET, OUTPUT_BUCKET]
    storage_client = S3StorageClient("test", "test", CONFIG.AWS_DEFAULT_REGION, endpoint_url=CONFIG.endpoint_url)

    # TODO: This removes buckets for every other test... need standalone buckets for end to end tests and inject them
    #   into the config.  However, the datasets themselves have reference to the bucket (sourceBucket) so need to
    #   reconcile that too.
    try:
        for bucket in buckets:
            storage_client.clear_bucket(bucket)
            storage_client.client.delete_bucket(Bucket=bucket)
    except:
        pass

    for bucket in buckets:
        storage_client.client.create_bucket(
            Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": CONFIG.AWS_DEFAULT_REGION}
        )

    upload_folder_to_s3(storage_client, INPUT_BUCKET, TEST_DATA_INPUT_DIR / "end_to_end")

    yield storage_client

    # teardown
    for bucket in buckets:
        storage_client.clear_bucket(bucket)
        storage_client.client.delete_bucket(Bucket=bucket)


def upload_folder_to_s3(storage_client, bucket, folder: Path) -> None:
    for file in folder.rglob("*.parquet"):
        key = str(file.relative_to(folder))
        storage_client.put_bytes(bucket, key, file.read_bytes())


@pytest.fixture
def mock_api_manager(monkeypatch) -> None:
    """Intercept metadata API calls and return JSON from local fixture files."""
    response_dict = all_metadata_api_data()

    def fake_make_api_call(self, url=None, params=None):
        req = requests.Request("GET", url, params=params)
        prepped = req.prepare()
        full_url = prepped.url
        response = response_dict[full_url]
        return response

    monkeypatch.setattr("new_processor.externals.api_manager.MetadataAPIManager.make_api_call", fake_make_api_call)

    # Because the test data JSON files are held individually per site, it's important to only process the configs 1 at
    # a time - hence explicitly set the batch size to 1:
    original_fn = new_processor.dag.dataset_dependency_graph.MetadataRouter.fetch_processing_configs

    def wrapped(dataset_ids, *args, **kwargs):
        kwargs["batch_size"] = 1
        return original_fn(dataset_ids, *args, **kwargs)

    monkeypatch.setattr(
        "new_processor.dag.dataset_dependency_graph.MetadataRouter.fetch_processing_configs",
        wrapped,
    )


class TestMain:
    """End-to-end test of the timeseries processor.

    Run a CLI based test for the timeseries processor and compare the outputs against a series of expected parquet
    files.

    This is designed to test running the processor end to end calling __main__.py from the command line
    as if it were being run by the user.

    It is assumed that the structure of the expected outputs will match the storage of the generated outputs on S3
    """

    def test_basic_end_to_end(self, storage_client, mock_api_manager) -> None:
        variables = ["TA"]
        cli_args = [
            "from-cross-product",
            "--sites",
            "cosmos-alic1",
            "--variables",
            " ".join(variables),
            "--periodicities",
            "PT30M",
            "--lookback",
            "P2D",
            "--network",
            "cosmos",
            "--end-date",
            "2024-03-09",
        ]

        # run the processor
        main(cli_args)

        # check the outputs
        expected_output_dir = TEST_DATA_OUTPUT_DIR / "end_to_end" / "existing"
        expected_path = expected_output_dir / "network=cosmos/date=2024-03-08/site=ALIC1/resolution=PT30M/data.parquet"

        expected_s3_key = str(expected_path.relative_to(expected_output_dir))
        result = pl.read_parquet(storage_client.get_bytes(OUTPUT_BUCKET, expected_s3_key))
        expected = pl.read_parquet(expected_output_dir / expected_s3_key)

        # TODO: Work out how to test the flags
        assert_frame_equal(result[variables + ["time"]], expected[variables + ["time"]])

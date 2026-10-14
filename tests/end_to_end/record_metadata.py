"""
Record and cache metadata API responses for end-to-end (E2E) testing.

This module is a one-off utility used to record all metadata responses required by the E2E test suite.
It runs against the real metadata API once, records every response that would be fetched during a processing run,
and saves those responses as JSON files.

The recorded JSON files allow E2E tests to run offline, without depending on the availability of the live metadata API.

How it works
------------
- A custom ``requests.Session`` (``MetadataCacheSession``) intercepts all HTTP requests made to the metadata API.
- Each response is written to disk using a stable filename, derived by encoding the full HTTP URL request that was
  made to the API.
- The script builds a full ``DatasetDependencyGraph`` for each E2E test case, ensuring that all metadata endpoints
  required by the processor are visited and cached.

Usage pattern
-------------
This script is not used during normal test execution. Instead, it should be run manually:
- when E2E test cases change
- when metadata API behaviour or schemas change

Once generated, the JSON files are treated as static test inputs and are loaded by the test suite in place of real API
calls.

Test cases listed in ``SKIPPED_TEST_CASES`` are not recorded, and their existing fixtures are kept. See the note there.
"""

import json
import logging
from pathlib import Path
from typing import Any

import requests
from driutils.metadata_api.api_manager import MetadataAPIManager
from tests.utils.fixture_helpers import END_TO_END, TEST_DATA_MOCK_METADATA, load_json_file
from tests.utils.metadata_helpers import E2E_INPUT_BUCKET, E2E_OUTPUT_BUCKET, stable_file_key

from dritimeseriesprocessor.cli.selection import DimensionSelection, Selection
from dritimeseriesprocessor.configuration.app_config import app_config
from dritimeseriesprocessor.dag.dataset_dependency_graph import DatasetDependencyGraph
from dritimeseriesprocessor.routers.metadata.metadata_router import MetadataRouter
from dritimeseriesprocessor.utils.urls import SITE_URI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Test cases whose metadata no longer exists in the metadata API, so can't be recorded again. Their fixtures are kept
# as they are, and recording them is skipped.
#
# NOTE: flux-plynl-eddypro - the flux sites and datasets were test records used while the system was being built, and
#   have since been removed from the metadata API. There are no live flux sites yet. Remove this entry and re-record
#   once real flux metadata is available.
SKIPPED_TEST_CASES = {"flux-plynl-eddypro"}


class MetadataCacheSession(requests.Session):
    """A requests.Session that intercepts calls to the metadata api and saves response to file for testing purposes."""

    def __init__(self) -> None:
        super().__init__()

    def request(self, method: str, url: str, **kwargs) -> requests.Response:  # type: ignore[override]
        """Intercept the API call, then send the request and cache its JSON response to file.

        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Forwarded to ``requests.Session.request``

        Returns:
            The response object returned by the parent session.
        """
        resp = super().request(method, url, **kwargs)

        # For end-to-end testing, we want to control where the data is written.
        # Overwrite the bucket names in the metadata JSON.
        metadata = rewrite_buckets(resp.json())

        file_key = stable_file_key(resp.url)

        output_filepath = TEST_DATA_MOCK_METADATA / (file_key + ".json")
        with open(output_filepath, "w") as output_file:
            json.dump(metadata, output_file, indent=2)

        return resp


def _rewrite_s3_uri(uri: Any) -> Any:
    """Rewrite an s3://bucket/... URI to use the appropriate E2E test bucket."""
    if not isinstance(uri, str) or not uri.startswith("s3://"):
        return uri
    without_scheme = uri[len("s3://") :]
    bucket, _, rest = without_scheme.partition("/")
    replacement = E2E_OUTPUT_BUCKET if "processed" in bucket else E2E_INPUT_BUCKET
    return f"s3://{replacement}/{rest}"


def rewrite_buckets(obj: Any) -> Any:
    """Recursively rewrite any sourceBucket fields to the known E2E test buckets.

    Some metadata responses include S3 bucket references. In E2E tests we want these to point at the local
    test buckets (input/output) rather than whatever bucket name is stored in the real metadata.

    Args:
        obj: Any JSON value (dict, list, str).

    Returns:
        A JSON value with bucket names renamed.
    """

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "sourceBucket":
                old_bucket = obj[key]
                if "processed" in old_bucket:
                    obj[key] = E2E_OUTPUT_BUCKET
                else:
                    obj[key] = E2E_INPUT_BUCKET
            elif key == "accessUrl" and isinstance(value, list):
                obj[key] = [_rewrite_s3_uri(v) for v in value]
            else:
                obj[key] = rewrite_buckets(value)

    if isinstance(obj, list):
        return [rewrite_buckets(v) for v in obj]

    return obj


def is_fixture_for_sites(fixture_path: Path, site_ids: set[str]) -> bool:
    """Check whether a recorded fixture belongs to any of the given sites, using the request URL it was recorded from.

    Args:
        fixture_path: Path to a recorded metadata fixture.
        site_ids: Site ids, e.g. `flux-plynl`.

    Returns:
        True if the fixture's request URL mentions one of the sites.
    """
    request_url = load_json_file(fixture_path).get("meta", {}).get("@id", "")
    return any(site_id in request_url for site_id in site_ids)


def reset_metadata_fixture_dir(path: Path, kept_site_ids: set[str]) -> None:
    """Delete the recorded fixtures in the metadata fixture directory, apart from those for the kept sites.

    Args:
        path: Directory path to reset.
        kept_site_ids: Sites whose fixtures are kept, because their test cases are not being recorded.
    """
    path.mkdir(parents=True, exist_ok=True)
    for fixture_path in path.glob("*.json"):
        if is_fixture_for_sites(fixture_path, kept_site_ids):
            logger.info(f"Keeping fixture for a skipped test case: {fixture_path.name}")
        else:
            fixture_path.unlink()


def main() -> None:
    """Populate the mock metadata fixture directory for all E2E test cases.

    This function:
    1. Creates a metadata API client that uses MetadataCacheSession to intercept outgoing metadata API requests
    2. Loads E2E test cases from test_cases.json.
    3. Clears the TEST_DATA_MOCK_METADATA directory, apart from the fixtures for the sites of skipped test cases.
    4. For each test case that is not skipped, builds a DatasetDependencyGraph, which triggers the metadata lookups that
       need to be cached.

    After this completes, the E2E test suite can be configured to use the recorded JSON fixtures instead of calling
    the live metadata API.
    """
    cfg = app_config()

    session = MetadataCacheSession()
    api_manager = MetadataAPIManager(cfg.metadata_api_url, session)
    metadata_router = MetadataRouter(cfg.metadata_api_url, api_manager)

    test_cases = load_json_file(END_TO_END / "test_cases.json")["test_cases"]
    skipped_site_ids = {
        site_id for test_case in test_cases if test_case["id"] in SKIPPED_TEST_CASES for site_id in test_case["sites"]
    }

    # reset metadata json
    reset_metadata_fixture_dir(TEST_DATA_MOCK_METADATA, skipped_site_ids)

    # for each test case, build dependency graph to trigger the metadata caching
    for test_case in test_cases:
        if test_case["id"] in SKIPPED_TEST_CASES:
            logger.info(f"Skipping recording for test_case: {test_case['id']} - see SKIPPED_TEST_CASES")
            continue
        try:
            logger.info(f"Recording metadata for test_case: {test_case['id']}")
            # the downstream processes requires full site uris rather than standalone IDs
            site_uris = [SITE_URI + "/" + site for site in test_case["sites"]]

            # discover all the variables that are needed for this test case
            variables = (
                test_case["measured_variables"] + test_case["derived_variables"] + test_case["aggregated_variables"]
            )

            # build the graph!
            selection: list[Selection] = [
                DimensionSelection(
                    network=test_case["network"],
                    sites=site_uris,
                    variables=variables,
                    periodicities=test_case["periodicities"],
                )
            ]
            graph = DatasetDependencyGraph(metadata_router, selection)
            graph.build()
        except Exception:
            logger.exception(f"Metadata recording failed for test_case: {test_case['id']}")


if __name__ == "__main__":
    logger.info("Starting metadata recording.")
    main()
    logger.info("Finished.")

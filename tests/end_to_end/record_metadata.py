import json
import requests
import shutil

from new_processor.externals.api_manager import MetadataAPIManager
from new_processor.configuration.app_config import app_config
from new_processor.routers.metadata.metadata_router import MetadataRouter
from tests.utils.fixture_helpers import TEST_DATA_MOCK_METADATA, END_TO_END, load_json_file
from new_processor.utils.urls import SITE_URI
from new_processor.dag.dataset_dependency_graph import DatasetDependencyGraph
from new_processor.cli.selection import SelectionOption
from tests.utils.metadata_helpers import stable_file_key, E2E_INPUT_BUCKET, E2E_OUTPUT_BUCKET


class MetadataCacheSession(requests.Session):
    """ A requests.Session that intercepts calls to the metadata api and saves response to file for testing purposes.
    """
    def __init__(self) -> None:
        super().__init__()

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        resp = super().request(method, url, **kwargs)
        metadata = rewrite_buckets(resp.json())

        file_key = stable_file_key(resp.url)

        output_filepath = TEST_DATA_MOCK_METADATA / (file_key + ".json")
        with open(output_filepath, "w") as output_file:
            json.dump(metadata, output_file, indent=2)

        return resp


def rewrite_buckets(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "sourceBucket":
                old_bucket = obj[key]
                if "processed" in old_bucket:
                    obj[key] = E2E_OUTPUT_BUCKET
                else:
                    obj[key] = E2E_INPUT_BUCKET
            else:
                obj[key] = rewrite_buckets(value)

    if isinstance(obj, list):
        return [rewrite_buckets(v) for v in obj]

    return obj


def main() -> None:
    """Update all metadata fixtures from the API."""
    cfg = app_config()
    session = MetadataCacheSession()
    api_manager = MetadataAPIManager(cfg.metadata_api_url, session)
    metadata_router = MetadataRouter(cfg.metadata_api_url, api_manager)

    # reset metadata json
    shutil.rmtree(TEST_DATA_MOCK_METADATA)
    TEST_DATA_MOCK_METADATA.mkdir()

    test_cases = load_json_file(END_TO_END / "test_cases.json")["test_cases"]

    for test_case in test_cases:
        test_case["sites"] = [SITE_URI + "/" + site for site in test_case["sites"]]

        variables = test_case["measured_variables"] + test_case["derived_variables"] + test_case["aggregated_variables"]

        selection = [SelectionOption(test_case["sites"], variables, test_case["periodicities"])]
        graph = DatasetDependencyGraph(
            network=test_case["network"], selection=selection, metadata_router=metadata_router
        )
        graph.build()


if __name__ == "__main__":
    main()
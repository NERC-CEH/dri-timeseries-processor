import re
from typing import Any
from urllib.parse import urlencode

from new_processor.utils.enums import ConfigurationType
from utils.fixture_helpers import TEST_DATA_MOCK_METADATA, load_json_file

BASE_URL = "https://dri-metadata-api.staging.eds.ceh.ac.uk/"
PERIOD_MAP = {
    "30min": "PT30M",
    "1day": "P1D",
}


def network_response():
    return {f"{BASE_URL}/id/network/cosmos": load_json_file(TEST_DATA_MOCK_METADATA / "network.json")}


def sites_response():
    metadata_dir = TEST_DATA_MOCK_METADATA / "sites"
    meta = {}
    for file in metadata_dir.glob("*.json"):
        url = f"{BASE_URL}id/site?" + urlencode(
            {"_view": "annotated", "@id": f"http://fdri.ceh.ac.uk/id/site/{file.stem}"}
        )
        meta[url] = load_json_file(file)
    return meta


def ts_datasets_response():
    metadata_dir = TEST_DATA_MOCK_METADATA / "ts_datasets"
    meta = {}
    for file in metadata_dir.rglob("*.json"):
        metadata = load_json_file(file)

        ds_id = file.stem
        url = f"{BASE_URL}id/dataset/{ds_id}?" + urlencode({"_view": "timeseries"})
        meta[url] = metadata

        regex = r"^(?P<site_id>[^-]+-[^-]+)-(?P<var>[^_]+)_(?P<period>[^_]+)_(?P<level>.+)$"
        match = re.match(regex, ds_id)

        url = f"{BASE_URL}id/dataset?" + urlencode(
            {
                "originatingSite": f"http://fdri.ceh.ac.uk/id/site/{match['site_id']}",
                "sourceColumnName": match["var"].upper(),
                "type.measure.aggregation.periodicity": PERIOD_MAP[match["period"]],
                "_view": "timeseries",
                "type.processingLevel": f"http://fdri.ceh.ac.uk/ref/common/processing-level/{match['level']}",
            }
        )
        meta[url] = metadata

    return meta


def ts_dependencies_response():
    metadata_dir = TEST_DATA_MOCK_METADATA / "ts_dependencies"
    meta = {}
    for file in metadata_dir.rglob("*.json"):
        url = f"{BASE_URL}id/dataset/{file.stem}/_all_dependencies"
        meta[url] = load_json_file(file)
    return meta


def ts_configurations_response():
    metadata_dir = TEST_DATA_MOCK_METADATA / "configurations"
    meta = {}

    for file in metadata_dir.rglob("*.json"):
        params = [
            ("type", f"http://fdri.ceh.ac.uk/ref/common/configuration-type/{config_type.value}")
            for config_type in ConfigurationType
        ]
        params.append(("appliesToTimeSeries", f"http://fdri.ceh.ac.uk/id/dataset/{file.stem}"))
        url = f"{BASE_URL}id/data-processing-configuration?" + urlencode(params)
        meta[url] = load_json_file(file)

    return meta


def all_metadata_api_data() -> dict[str, Any]:
    data = {}

    data |= network_response()
    data |= sites_response()
    data |= ts_datasets_response()
    data |= ts_dependencies_response()
    data |= ts_configurations_response()

    return data

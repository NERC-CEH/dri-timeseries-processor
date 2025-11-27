from pathlib import Path
from typing import Any

from utils.fixture_helpers import load_json_file, TEST_DATA_MOCK_METADATA


BASE_URL = "https://dri-metadata-api.staging.eds.ceh.ac.uk/"


def default_metadata_api_data() -> dict[str, Any]:
    base_url = "https://dri-metadata-api.staging.eds.ceh.ac.uk/"
    url_map = {
        "sites_metadata.json": "id/network/cosmos",
        "ts_id_metadata_alic1_bunny.json": "id/dataset",
        "ts_def_metadata.json": "ref/time-series-definition",
        "processing_configs_alic1_bunny.json": "id/data-processing-configuration.json",
    }

    return {
        f"{base_url}{url_path}": load_json_file(TEST_DATA_MOCK_METADATA / filename)
        for filename, url_path in url_map.items()
    }


def load_all_api_data_from_folder(base_dir: Path, base_url: str, suffix: str = "") -> dict[str, Any]:
    """Load all JSON files in base_dir into a URL → JSON dict."""
    return {
        f"{base_url}{file.stem}{suffix}": file.read_text()
        for file in base_dir.glob("*.json")
    }


def all_metadata_api_data() -> dict[str, Any]:
    data = default_metadata_api_data()

    data |= load_all_api_data_from_folder(
        TEST_DATA_MOCK_METADATA / "ts_dependencies",
        "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos",
        "/_dependencies",
    )

    data |= load_all_api_data_from_folder(
        TEST_DATA_MOCK_METADATA / "correction_configurations",
        "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/"
        "data-processing-configuration.json?type=http://fdri.ceh.ac.uk/ref/common/configuration-type/"
        "correction-configuration&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos",
    )

    data |= load_all_api_data_from_folder(
        TEST_DATA_MOCK_METADATA / "infill_configurations",
        "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/"
        "data-processing-configuration.json?type=http://fdri.ceh.ac.uk/ref/common/configuration-type/"
        "infill-configuration&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos",
    )

    data |= load_all_api_data_from_folder(
        TEST_DATA_MOCK_METADATA / "qc_configurations",
        "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/"
        "data-processing-configuration.json?type=http://fdri.ceh.ac.uk/ref/common/configuration-type/"
        "qc&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos",
    )

    return data
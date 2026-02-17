"""
Fetch latest metadata JSON from the live API for specific files used in unit tests.

Only needs to run when metadata has changed.
"""

# ruff: noqa

import json
import logging

from tests.utils.fixture_helpers import TEST_DATA_API_VALID

from dritimeseriesprocessor.externals.api_manager import MetadataAPIManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

BASE_URL = "https://dri-metadata-api-dev.staging.eds.ceh.ac.uk"
MAPPING = {
    "data_processing_configuration": {
        "cosmos_bunny_lwin_30min_raw_correction.json": f"{BASE_URL}/id/data-processing-configuration?type=http://fdri.ceh.ac.uk/ref/common/configuration-type/correction-configuration&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-lwin_30min_raw",
        "cosmos_bunny_swin_30min_raw_correction.json": f"{BASE_URL}/id/data-processing-configuration?type=http://fdri.ceh.ac.uk/ref/common/configuration-type/correction-configuration&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-swin_30min_raw",
        "cosmos_bunny_swin_30min_raw_infill.json": f"{BASE_URL}/id/data-processing-configuration?type=http://fdri.ceh.ac.uk/ref/common/configuration-type/infill-configuration&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-swin_30min_raw",
        "cosmos_bunny_swin_30min_raw_qc.json": f"{BASE_URL}/id/data-processing-configuration?type=http://fdri.ceh.ac.uk/ref/common/configuration-type/qc&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-swin_30min_raw",
    },
    "dataset_timeseries": {
        "cosmos_bunny_precip_30min_raw.json": f"{BASE_URL}/id/dataset/cosmos-bunny-precip_30min_raw.json?_view=timeseries",
        "cosmos_bunny_rn_1day_processed.json": f"{BASE_URL}/id/dataset/cosmos-bunny-rn_1day_processed.json?_view=timeseries",
        "cosmos_bunny_swin_30min_processed.json": f"{BASE_URL}/id/dataset/cosmos-bunny-swin_30min_processed.json?_view=timeseries",
        "cosmos_bunny_ta_30min_raw.json": f"{BASE_URL}/id/dataset/cosmos-bunny-ta_30min_raw.json?_view=timeseries",
    },
    "network": {
        "cosmos.json": f"{BASE_URL}/id/network/cosmos.json",
        "fdri.json": f"{BASE_URL}/id/network/fdri.json",
        "nrfa.json": f"{BASE_URL}/id/network/nrfa.json",
    },
    "site": {
        "cosmos_bunny.json": f"{BASE_URL}/id/site/cosmos-bunny.json",
        "fdri_carreg-wen.json": f"{BASE_URL}/id/site/fdri-se-carwe-01.json",
        "nrfa_40018.json": f"{BASE_URL}/id/site/nrfa-40018.json",
    },
    "deployment": {
        "cosmos-bunny-aws_anem.json": f"{BASE_URL}/id/deployment/cosmos-bunny-aws_anem-aws_anem-140810-2.json",
        "cosmos-elmst-tdt8-tdt.json": f"{BASE_URL}/id/deployment/cosmos-elmst-tdt8-tdt-6503264-1.json",
        "fdri-se-carwe-01-ws-801.json": f"{BASE_URL}/id/deployment/fdri-se-carwe-01-ws-801.json",
    },
}


def main() -> None:
    api_manager = MetadataAPIManager(BASE_URL)

    for subdir, file_map in MAPPING.items():
        for filename, metadata_url in file_map.items():
            output_filepath = TEST_DATA_API_VALID / subdir / filename
            output_filepath.parent.mkdir(parents=True, exist_ok=True)
            metadata = api_manager.make_api_call(metadata_url)
            with open(output_filepath, "w") as output_file:
                json.dump(metadata, output_file, indent=2)


if __name__ == "__main__":
    main()

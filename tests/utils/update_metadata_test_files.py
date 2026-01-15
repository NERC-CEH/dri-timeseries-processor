"""
Fetch latest metadata JSON from the live API for specific files used in unit tests.

Only needs to run when metadata has changed.
"""

import json
import logging

from tests.utils.fixture_helpers import TEST_DATA_API_VALID

from dritimeseriesprocessor.configuration.app_config import app_config
from dritimeseriesprocessor.externals.api_manager import MetadataAPIManager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


MAPPING = {
    "data_processing_configuration": {
        "cosmos_bunny_lwin_30min_raw_correction.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration?type=http://fdri.ceh.ac.uk/ref/common/configuration-type/correction-configuration&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-lwin_30min_raw",
        "cosmos_bunny_swin_30min_raw_correction.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration?type=http://fdri.ceh.ac.uk/ref/common/configuration-type/correction-configuration&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-swin_30min_raw",
        "cosmos_bunny_swin_30min_raw_infill.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration?type=http://fdri.ceh.ac.uk/ref/common/configuration-type/infill-configuration&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-swin_30min_raw",
        "cosmos_bunny_swin_30min_raw_qc.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration?type=http://fdri.ceh.ac.uk/ref/common/configuration-type/qc&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-swin_30min_raw",
    },
    "dataset_dependencies": {
        "cosmos_bunny_precip_30min_processed.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-bunny-precip_30min_processed/_dependencies.json",
        "cosmos_bunny_precip_30min_raw.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-bunny-precip_30min_raw/_dependencies.json",
        "cosmos_bunny_rn_30min_processed.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-bunny-rn_30min_processed/_dependencies.json",
        "cosmos_bunny_rn_30min_processed_all.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-bunny-rn_30min_processed/_all_dependencies.json",
        "cosmos_bunny_swin_30min_processed.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-bunny-swin_30min_processed/_dependencies.json",
        "cosmos_bunny_swin_30min_raw.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-bunny-swin_30min_raw/_dependencies.json",
    },
    "dataset_timeseries": {
        "cosmos_bunny_precip_30min_raw.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-bunny-precip_30min_raw.json?_view=timeseries",
        "cosmos_bunny_rn_1day_processed.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-bunny-rn_1day_processed.json?_view=timeseries",
        "cosmos_bunny_swin_30min_processed.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-bunny-swin_30min_processed.json?_view=timeseries",
        "cosmos_bunny_ta_30min_raw.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-bunny-ta_30min_raw.json?_view=timeseries",
    },
    "network": {
        "cosmos.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/network/cosmos.json",
        "fdri.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/network/fdri.json",
        "nrfa.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/network/nrfa.json",
    },
    "site": {
        "cosmos_bunny.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/site/cosmos-bunny.json",
        "fdri_carreg-wen.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/site/fdri-se-carwe-01.json",
        "nrfa_40018.json": "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/site/nrfa-40018.json",
    },
}


def main():
    cfg = app_config()
    api_manager = MetadataAPIManager(cfg.metadata_api_url)

    for dir, file_map in MAPPING.items():
        for filename, metadata_url in file_map.items():
            output_filepath = TEST_DATA_API_VALID / dir / filename

            metadata = api_manager.make_api_call(metadata_url)
            with open(output_filepath, "w") as output_file:
                json.dump(metadata, output_file, indent=2)


if __name__ == "__main__":
    main()

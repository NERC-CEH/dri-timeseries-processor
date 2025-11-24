from pathlib import Path

from driutils.metadata_api.api_manager import MetadataAPIManager

from dritimeseriesprocessor.configuration import app_config

METADATA_CONNECTION = MetadataAPIManager(host=app_config.metadata_api_url, network="cosmos")

METADATA_URLS = [
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/network/cosmos",
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset",
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/ref/time-series-definition",
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json",
]

BASE_DIR = Path()

FILE_MAPPING = {
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/network/cosmos": "sites_metadata.json",
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset": "ts_id_metadata_alic1_bunny.json",
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/ref/time-series-definition": "",
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json": "",
}

""" NOTES - DELETE LATER
Sites:
    - ALIC1, BUNNY
    - need all correction configurations, infill_configs, qc_configs, and ts_deps

- how to automate file structure?

"""
SITES = ["ALIC1", "BUNNY"]
VARIABLES = [
    "battv",
    "g1",
    "g2",
    "lwin",
    "lwout",
    "pa",
    "rh",
    "scans",
    "swin",
    "ta",
    "tnr01c",
    "ws"
]

def main():
    update_mock_metadata_response()


def update_mock_metadata_response():

    # Update metadata for any 
    for url, file_path in FILE_MAPPING.items():
        response = 

    pass


if __name__ == "__main__":
    main()

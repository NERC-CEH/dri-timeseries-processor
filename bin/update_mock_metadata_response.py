import asyncio
import json
from pathlib import Path

from driutils.metadata_api.api_manager import MetadataAPIManager

from dritimeseriesprocessor.configuration import app_config

loop = asyncio.get_event_loop()

METADATA_CONNECTION = MetadataAPIManager(host=app_config.metadata_api_url, network="cosmos")

BASE_DIR = Path(__file__).parents[1].joinpath("testing", "data", "inputs", "mock_metadata_api")

FILE_MAPPING = {
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/network/cosmos": "sites_metadata.json",
    (
        "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset.json?_limit=10000000&_view=timeseries"
        "&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-alic1"
        "&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-bunny"
    ): "ts_id_metadata_alic1_bunny.json",
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/ref/time-series-definition": "ts_def_metadata.json",
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json": (
        "processing_configs_alic1_bunny.json"
    ),
}


# Combinations of variables and periods which are needed for all sites.
SITES = ["alic1", "bunny"]
VARIABLES = ["battv", "g1", "g2", "lwin", "lwout", "pa", "rh", "scans", "swin", "ta", "tnr01c", "ws"]
PERIODS = ["30min"]

EXTRA_VARIABLES = []

# Mapping
MULTI_FILE_BASE_URLS_MAPPING = {
    # Correction Configurations
    (
        "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json?type=http://fdri."
        "ceh.ac.uk/ref/common/configuration-type/correction-configuration&appliesToTimeSeries=http://fdri.ceh.ac."
        "uk/id/dataset/cosmos-"
    ): "correction_configurations",
    # Infill Configurations
    (
        "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json?type=http://fdri."
        "ceh.ac.uk/ref/common/configuration-type/infill-configuration&appliesToTimeSeries=http://fdri.ceh.ac.uk/"
        "id/dataset/cosmos-"
    ): "infill_configurations",
    # QC Configurations
    (
        "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json?type=http://fdri."
        "ceh.ac.uk/ref/common/configuration-type/qc&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos-"
    ): "qc_configurations",
}


def main() -> None:
    update_mock_metadata_response()


def update_mock_metadata_response() -> None:
    print("Starting")
    # Update metadata for any urls where the output is stored in a single file
    for url, file_name in FILE_MAPPING.items():
        print(f"Updating data for: {url}")
        save_response_to_file(url=url, output_filepath=BASE_DIR.joinpath(file_name))

    # Update urls that need outputs storing on a single-file-per-variable basis
    for base_url, base_dirname in MULTI_FILE_BASE_URLS_MAPPING.items():
        update_multi_file_urls(base_url=base_url, output_dir=BASE_DIR.joinpath(base_dirname))

        # Collect updated data for any specific variables which don't fit the generic site/variable/period pattern.
        # For example if only one variable from a site is required (e.g. wrttl-ta_1day_raw)
        for variable in EXTRA_VARIABLES:
            url = f"{base_url}{variable}"
            print("Updating: {url}")
            save_response_to_file(url=url, output_filepath=BASE_DIR.joinpath(f"{variable}.json"))

    print("Finished")


def update_multi_file_urls(base_url: str, output_dir: str) -> None:
    for site in SITES:
        for variable in VARIABLES:
            for period in PERIODS:
                # Its assumed that all variables are raw for multi-file urls
                basename = f"{site}-{variable}_{period}_raw"
                url = f"{base_url}{basename}"

                print(f"Updating data for: {url}")
                save_response_to_file(url=url, output_filepath=output_dir.joinpath(f"{basename}.json"))


def save_response_to_file(url: str, output_filepath: str) -> None:
    response = loop.run_until_complete(METADATA_CONNECTION._make_paginated_api_call(url))

    with open(output_filepath, "w") as output_file:
        json.dump(response, output_file, indent=2)


if __name__ == "__main__":
    main()

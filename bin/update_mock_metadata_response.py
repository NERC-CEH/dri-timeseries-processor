METADATA_URLS = [
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/network/cosmos",
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset",
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/ref/time-series-definition",
    "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json",
]

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

def main():
    update_mock_metadata_response()


def update_mock_metadata_response():
    pass


if __name__ == "__main__":
    main()

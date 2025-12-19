import json
from pathlib import Path

from new_processor.externals.api_manager import MetadataAPIManager
from new_processor.configuration.app_config import app_config
from new_processor.utils.enums import ConfigurationType
from tests.utils.fixture_helpers import TEST_DATA_MOCK_METADATA
from tests.utils.metadata_helpers import BASE_URL

cfg = app_config()
METADATA_CONNECTION = MetadataAPIManager(host=cfg.metadata_api_url)

SITES = ["cosmos-alic1", "cosmos-bunny"]
VARIABLES = ["battv", "g1", "g2", "lwin", "lwout", "pa", "rh", "scans", "swin", "ta", "tnr01c", "ws"]
PERIODS = ["30min"]
LEVELS = ["raw", "processed"]


def main() -> None:
    """Update all metadata fixtures from the API."""
    print("Starting metadata update")

    updaters = [
        update_network_response,
        update_sites_response,
        update_config_response,
        update_dataset_response,
        update_dataset_dependencies_response,
    ]

    for updater in updaters:
        updater()

    print("Completed all updates")


def update_network_response() -> None:
    """Update network metadata fixture."""
    url = "id/network/cosmos"
    filepath = TEST_DATA_MOCK_METADATA / "network.json"
    print(f"Updating network data: {url}")
    save_response_to_file(url=url, output_filepath=filepath)


def update_sites_response() -> None:
    """Update site metadata fixtures for all sites."""
    output_dir = TEST_DATA_MOCK_METADATA / "sites"
    base_url = "id/site?_view=annotated"

    for site in SITES:
        url = f"{base_url}&@id=http://fdri.ceh.ac.uk/id/site/{site}"
        filepath = output_dir / f"{site}.json"
        print(f"Updating site data: {site}")
        save_response_to_file(url=url, output_filepath=filepath)


def update_config_response() -> None:
    """Update configuration metadata fixtures for all combinations."""
    output_dir = TEST_DATA_MOCK_METADATA / "configurations"

    all_types = [f"type=http://fdri.ceh.ac.uk/ref/common/configuration-type/{config_type.value}" for config_type in ConfigurationType]

    base_url = (
        f"id/data-processing-configuration.json?"
        + "&".join(all_types) +
        f"&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/"
    )

    _update_dataset_combinations(
        output_dir=output_dir,
        base_url=base_url,
        description=f"configuration"
    )


def update_dataset_response() -> None:
    """Update dataset metadata fixtures for all combinations."""
    output_dir = TEST_DATA_MOCK_METADATA / "ts_datasets"
    base_url = "id/dataset/"
    suffix = "?_view=timeseries"

    _update_dataset_combinations(
        output_dir=output_dir,
        base_url=base_url,
        suffix=suffix,
        description="dataset"
    )


def update_dataset_dependencies_response() -> None:
    """Update dataset dependencies metadata fixtures for all combinations."""
    output_dir = TEST_DATA_MOCK_METADATA / "ts_dependencies"
    base_url = "id/dataset/"
    suffix = "/_all_dependencies"

    _update_dataset_combinations(
        output_dir=output_dir,
        base_url=base_url,
        suffix=suffix,
        description="dataset dependencies"
    )


def _update_dataset_combinations(
        output_dir: Path,
        base_url: str,
        suffix: str = "",
        description: str = "data"
) -> None:
    """
    Update metadata for all site/variable/period/level combinations.

    Args:
        output_dir: Directory to save the JSON files
        base_url: Base URL for the API endpoint
        suffix: Optional URL suffix to append
        description: Description for logging purposes
    """
    for site in SITES:
        for variable in VARIABLES:
            for period in PERIODS:
                for level in LEVELS:
                    basename = f"{site}-{variable}_{period}_{level}"
                    url = f"{base_url}{basename}{suffix}"
                    filepath = output_dir / site / f"{basename}.json"

                    print(f"Updating {description}: {basename}")
                    try:
                        save_response_to_file(url=url, output_filepath=filepath)
                    except Exception as e:
                        print(f"Failed to update {basename}: {e}")


def save_response_to_file(url: str, output_filepath: Path) -> None:
    """
    Fetch data from API and save to JSON file.

    Args:
        url: API endpoint URL (relative to BASE_URL)
        output_filepath: Path where JSON response will be saved
    """
    response = METADATA_CONNECTION.make_paginated_api_call(BASE_URL + url)

    output_filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(output_filepath, "w") as output_file:
        json.dump(response, output_file, indent=2)


if __name__ == "__main__":
    main()
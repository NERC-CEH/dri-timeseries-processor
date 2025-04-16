import asyncio
import json
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dritimeseriesprocessor.configuration import app_config
from metadata_manager import api_manager
from metadata_manager.models.configs.infilling import InfillingConfig, InfillingProcessConfigs
from metadata_manager.models.methods.infilling_methods import InfillingMethodRegistry
from metadata_manager.models.schemas.derivations import Methodology, TimeseriesDerivationResponse
from metadata_manager.models.schemas.sites import SitesResponse
from metadata_manager.models.schemas.time_series import TimeSeriesMetadataResponse
from metadata_manager.transformers import extract_timeseries_definition_metadata

METADATA_CONNECTION = api_manager.MetadataAPIManager(host=app_config.metadata_api_url, network="cosmos")


class ConfigType(Enum):
    INFILLING = "infilling"
    CORRECTION = "correction"  # placeholder for moving other configs across


def load_config(config_type: Union[ConfigType, str]) -> Optional[Dict[str, Dict[str, InfillingConfig]]]:
    """Load configuration data based on the given configuration type.

    Args:
        config_type: The type of configuration to load.

    Returns:
        The parsed configurations.
    """
    if isinstance(config_type, str):
        config_type = ConfigType(config_type)

    if config_type == ConfigType.INFILLING:
        # TODO: To decide how to filter down (and at what stage to filter).  E.g. do we provide this function with
        #         a network name, and/or site name, and/or infilling method?
        metadata = api_manager.MetadataAPIManager(host=app_config.metadata_api_url, network="cosmos")
        data = asyncio.run(metadata.fetch_infill_configs())
        infilling_configs = InfillingProcessConfigs.model_validate(data)

        # Add in the time-series metadata.
        # TODO: Might not need to do this as might include this info in the config api view.
        #   In which case, this dictionary can be built in the InfillingProcessConfigs object.
        result = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for config in infilling_configs:
            site_id = config.site_id
            time_series_meta = load_timeseries(config.time_series_name)
            column = time_series_meta.column
            resolution = time_series_meta.measure.resolution

            result[site_id][resolution][column].append(config)

        return result


def load_methods(config_type: Union[ConfigType, str]) -> Optional[InfillingMethodRegistry]:
    """Load method definitions based on the given configuration type.

    Args:
        config_type: The type of configuration methods to load.

    Returns:
        The parsed methods.
    """
    if isinstance(config_type, str):
        config_type = ConfigType(config_type)

    if config_type == ConfigType.INFILLING:
        with open(Path(__file__).parent.absolute() / "methods" / "infilling_methods.json", "r") as f:
            data = json.load(f)
        return InfillingMethodRegistry.model_validate(data)


def load_timeseries(timeseries_id: Optional[str] = None) -> TimeSeriesMetadataResponse:
    """Load time series metadata from the API.

    Args:
        timeseries_id: Optional ID to fetch a specific time series

    Returns:
        The parsed time series metadata.
    """
    metadata = api_manager.MetadataAPIManager(host=app_config.metadata_api_url, network="cosmos")
    data = asyncio.run(metadata.fetch_timeseries_metadata(timeseries_id=timeseries_id))
    return TimeSeriesMetadataResponse.model_validate(data)


def load_datasets(parameters: Dict) -> Any:
    """Load dataset metadata from the API.

    Args:
        parameters: API query parameters for the dataset endpoint

    Returns:
        The parsed dataset metadata.
    """
    data = asyncio.run(METADATA_CONNECTION.fetch_dataset_metadata(parameters))
    # TODO build and test pydantic model for dataset return FW-696
    # NOTE The Pydantic model may need to vary depending on the view used in the API call.
    # Add as return annotation
    return data


def load_timeseries_derivation(timeseries_def: str) -> TimeseriesDerivationResponse:
    """Load the derivation metadata for a particular timeseries definition.

    Args:
        timeseries_def: The timeseries definition

    Returns:
        The parsed dataset metadata.
    """
    data = asyncio.run(METADATA_CONNECTION.fetch_timeseries_derivation_metadata(timeseries_def))
    return TimeseriesDerivationResponse.model_validate(data)


def handle_derivation_response(timeseries_def: str) -> Dict[str, Union[Dict[str, Union[str, List[str]]] | None]]:
    """Wrapper to handle the timeseries derivation service and transformation functionality

    Args:
        timeseries_def: the timeseries definition

    Returns:
        A dictionary containing the transfomred meatdata form the API response.
    """

    # Validate API response for the definition
    derivation_metadata = load_timeseries_derivation(timeseries_def)

    # If the response has a methodology section then it will contain
    # some dependencies that need checking.
    # Extract the required metadata
    metadata = extract_timeseries_definition_metadata(derivation_metadata)

    return metadata


def load_nested_timeseries_derivations(ts_defs: List[str]) -> Dict[str, Union[Methodology | None]]:
    """Recursively loads all timeseries derivation metadata for timeseries definitions.

    Each timeseries definition will have a dataset(s) that that need to be
    processed before it can be built. In turn, these datasets could be dependent
    on other datasets. And so on. Extract all derivation metadata for every dependent
    dataset.

    Args:
        ts_defs: A list of timeseries definitions to extract metadata for

    Returns:
        A dict containing transformed metadata from the response
    """
    # Somewhere to store all ts_defs and their inputs (uses)
    derivations = {}

    for ts_def in ts_defs:
        # For each pass we will generate a new set of inputs to check
        # When this becomes empty, we can stop checking for dependencies
        new_inputs_to_check = []

        # Create the first set of inputs to check.
        # We will check one parent ts_def at a time.
        # As its only one, we need to make this a list.
        # This will be replaced by new_inputs_to_check at the end of
        # every iteration
        inputs_to_check = [ts_def]

        # Keep checking until inputs_to_check contains no values
        while len(inputs_to_check) != 0:
            for item in inputs_to_check:
                # Extract the required metadata
                metadata = handle_derivation_response(item)

                # Build dict for defs map (if it doesnt already exist)
                if item not in derivations:
                    # Transform the response
                    derivations[item] = metadata

                    # Add the dependencies to the list to be check next time
                    new_inputs_to_check += derivations[item]["methodology"]["inputs"]

            # Update the inputs to be checked to the ones extracted in this loop
            inputs_to_check = new_inputs_to_check

            # Reset the new inputs
            new_inputs_to_check = []

    return derivations


def load_sites() -> SitesResponse:
    """Validate and load the sites endpoint response.

    Returns:
        The parsed sites metadata.
    """
    data = asyncio.run(METADATA_CONNECTION.fetch_sites())
    return SitesResponse.model_validate(data)

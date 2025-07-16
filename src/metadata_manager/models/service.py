import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional, Union

from dritimeseriesprocessor.configuration import app_config
from metadata_manager import api_manager
from metadata_manager.models.common import ComponentType
from metadata_manager.models.methods.method_registry import CorrectionMethods, DerivationMethods, InfillingMethods, QcMethods
from metadata_manager.models.schemas.data_processing_configurations import DataProcessingConfigurations
from metadata_manager.models.schemas.datasets import TimeseriesDatasetResponse
from metadata_manager.models.schemas.derivations import TimeseriesDerivationResponse
from metadata_manager.models.schemas.sites import SitesResponse
from metadata_manager.models.schemas.time_series import TimeSeriesMetadataResponse
from metadata_manager.transformers import extract_timeseries_definition_metadata

METADATA_CONNECTION = api_manager.MetadataAPIManager(host=app_config.metadata_api_url, network="cosmos")



def load_config(config_type: Union[ComponentType, str], ts_id: str) -> Optional[DataProcessingConfigurations]:
    """Load configuration data based on the given configuration type.

    Args:
        config_type: The type of configuration to load.
        ts_id: The time series ID to load configurations for.

    Returns:
        The parsed configurations.
    """
    if isinstance(config_type, str):
        config_type = ComponentType(config_type)

    if config_type == ComponentType.INFILLING:
        data = asyncio.run(METADATA_CONNECTION.fetch_infill_config(ts_id))
        infill_config = DataProcessingConfigurations.model_validate(data)
        return infill_config

    elif config_type == ComponentType.QUALITY_CONTROL:
        data = asyncio.run(METADATA_CONNECTION.fetch_qc_config(ts_id))
        qc_config = DataProcessingConfigurations.model_validate(data)
        return qc_config

    elif config_type == ComponentType.CORRECTION:
        data = asyncio.run(METADATA_CONNECTION.fetch_correction_config(ts_id))
        correction_config = DataProcessingConfigurations.model_validate(data)
        return correction_config

    else:
        return None


def load_methods(config_type: Union[ComponentType, str]) -> Optional[InfillingMethods | QcMethods | CorrectionMethods]:
    """Load method definitions based on the given configuration type.

    Args:
        config_type: The type of configuration methods to load.

    Returns:
        The parsed methods.
    """
    if isinstance(config_type, str):
        config_type = ComponentType(config_type)

    config_dir = Path(__file__).parent.absolute() / "methods"

    if config_type == ComponentType.INFILLING:
        methods_json_file = config_dir / "infilling_methods.json"
        registry = InfillingMethods

    elif config_type == ComponentType.QUALITY_CONTROL:
        methods_json_file = config_dir / "qc_methods.json"
        registry = QcMethods

    elif config_type == ComponentType.CORRECTION:
        methods_json_file = config_dir / "correction_methods.json"
        registry = CorrectionMethods

    elif config_type == ComponentType.DERIVATION:
        methods_json_file = config_dir / "derivation_methods.json"
        registry = DerivationMethods

    else:
        return None

    with open(methods_json_file, "r") as f:
        return registry.model_validate(json.load(f))


def load_timeseries(timeseries_id: Optional[str] = None) -> TimeSeriesMetadataResponse:
    """Load time series metadata from the API.

    Args:
        timeseries_id: Optional ID to fetch a specific time series

    Returns:
        The parsed time series metadata.
    """
    data = asyncio.run(METADATA_CONNECTION.fetch_timeseries_metadata(timeseries_id=timeseries_id))
    return TimeSeriesMetadataResponse.model_validate(data)


def load_datasets(parameters: Dict) -> TimeseriesDatasetResponse:
    """Load dataset metadata from the API.

    Args:
        parameters: API query parameters for the dataset endpoint

    Returns:
        The parsed dataset metadata.
    """
    data = asyncio.run(METADATA_CONNECTION.fetch_dataset_metadata(parameters))
    return TimeseriesDatasetResponse.model_validate(data)


def load_timeseries_derivation(timeseries_def: str) -> TimeseriesDerivationResponse:
    """Load the derivation metadata for a particular timeseries definition.

    Args:
        timeseries_def: The timeseries definition

    Returns:
        The parsed dataset metadata.
    """
    data = asyncio.run(METADATA_CONNECTION.fetch_timeseries_derivation_metadata(timeseries_def))
    return TimeseriesDerivationResponse.model_validate(data)


def handle_derivation_response(timeseries_def: str) -> Dict[str, Union[str, List[str | None]]]:
    """Wrapper to handle the timeseries derivation service and transformation functionality

    Args:
        timeseries_def: the timeseries definition

    Returns:
        A dictionary containing the transformed metadata from the API response.
    """

    # Validate API response for the definition
    derivation_metadata = load_timeseries_derivation(timeseries_def)

    # If the response has a methodology section then it will contain
    # some dependencies that need checking.
    # Extract the required metadata
    metadata = extract_timeseries_definition_metadata(derivation_metadata)

    return metadata


def load_nested_timeseries_derivations(ts_defs: List[str]) -> Dict[str, Dict[str, Union[str, List[str | None]]]]:
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
        # Create the first set of inputs to check.
        # We will check one parent ts_def at a time.
        # As its only one, we need to make this a list.
        # This will be replaced by new_inputs_to_check at the end of
        # every iteration
        inputs_to_check = [ts_def]

        # Keep checking until inputs_to_check contains no values
        while len(inputs_to_check) != 0:
            # Reset the new inputs
            new_inputs_to_check = []

            for item in inputs_to_check:
                # Extract the required metadata
                metadata = handle_derivation_response(item)

                # Build dict for defs map (if it doesnt already exist)
                if item not in derivations:
                    # Transform the response
                    derivations[item] = metadata

                    # Add the dependencies to the list to be check next time
                    new_inputs_to_check += derivations[item]["inputs"]

            # Update the inputs to be checked to the ones extracted in this loop
            inputs_to_check = new_inputs_to_check

    return derivations


def load_sites() -> SitesResponse:
    """Validate and load the sites endpoint response.

    Returns:
        The parsed sites metadata.
    """
    data = asyncio.run(METADATA_CONNECTION.fetch_sites())
    return SitesResponse.model_validate(data)

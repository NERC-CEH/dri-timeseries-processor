import asyncio
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Union

from dritimeseriesprocessor.configuration import app_config
from metadata_manager import api_manager
from metadata_manager.models.common import ComponentType
from metadata_manager.models.methods.method_registry import (
    AggregationMethods,
    CorrectionMethods,
    DerivationMethods,
    InfillingMethods,
    QcMethods,
)
from metadata_manager.models.schemas.data_processing_configurations import DataProcessingConfigurations
from metadata_manager.models.schemas.datasets import TimeseriesDatasetResponse
from metadata_manager.models.schemas.dependencies import (
    DependentTimeSeriesMetadata,
    DependentTimeSeriesMetadataResponse,
)
from metadata_manager.models.schemas.derivations import TimeseriesDerivationResponse
from metadata_manager.models.schemas.sites import SitesResponse
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

    elif config_type == ComponentType.AGGREGATION:
        methods_json_file = config_dir / "aggregation_methods.json"
        registry = AggregationMethods

    else:
        return None

    with open(methods_json_file, "r") as f:
        return registry.model_validate(json.load(f))


def load_datasets(parameters: Dict) -> TimeseriesDatasetResponse:
    """Load dataset metadata from the API.

    Args:
        parameters: API query parameters for the dataset endpoint

    Returns:
        The parsed dataset metadata.
    """
    data = asyncio.run(METADATA_CONNECTION.fetch_timeseries_metadata(parameters))
    return TimeseriesDatasetResponse.model_validate(data)


def load_dependent_datasets(timeseries_id: str) -> List[DependentTimeSeriesMetadata]:
    """Recursively load dataset metadata from the API for all input dependencies of the provided timeseries id.

    Args:
        timeseries_id: The id of the timeseries to identify dependent timeseries datasets for.

    Returns:
        List of dependent time series metadata objects for the provided timeseries id

    """
    data = asyncio.run(METADATA_CONNECTION.fetch_dependent_dataset_metadata(timeseries_id))

    # Use a separate list for storing the final output to prevent it being extended in situ when recursively checking
    # for sub dependencies#
    ts_dependency_list = []

    dependent_timeseries = DependentTimeSeriesMetadataResponse.model_validate(data)
    ts_dependency_list.extend(dependent_timeseries)

    # Iterate through the list of DependentTimeSeriesMetadata objects, checking to see if any have sub dependencies
    # before fetching them
    for dependent_ts in dependent_timeseries:
        sub_dependencies = load_dependent_datasets(dependent_ts.name)
        ts_dependency_list.extend(sub_dependencies)

    return ts_dependency_list


def load_timeseries_derivation(timeseries_def: str) -> TimeseriesDerivationResponse:
    """Load the derivation metadata for a particular timeseries definition.

    Args:
        timeseries_def: The timeseries definition

    Returns:
        The parsed dataset metadata.
    """
    data = asyncio.run(METADATA_CONNECTION.fetch_timeseries_derivation_metadata(timeseries_def))
    return TimeseriesDerivationResponse.model_validate(data)


@lru_cache(maxsize=100)
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


def load_sites() -> SitesResponse:
    """Validate and load the sites endpoint response.

    Returns:
        The parsed sites metadata.
    """
    data = asyncio.run(METADATA_CONNECTION.fetch_sites())
    return SitesResponse.model_validate(data)

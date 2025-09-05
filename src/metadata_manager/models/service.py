import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from dritimeseriesprocessor.configuration import app_config
from metadata_manager.api_manager import MetadataAPIManager
from metadata_manager.models.common import (
    URI_ID_EXTRACT_REGEX,
    ComponentType,
    build_processing_config_type_query_parameter,
)
from metadata_manager.models.methods.method_registry import (
    AggregationMethods,
    CorrectionMethods,
    DerivationMethods,
    InfillingMethods,
    QcMethods,
)
from metadata_manager.models.schemas.data_processing_configurations import (
    DataProcessingConfiguration,
    DataProcessingConfigurations,
)
from metadata_manager.models.schemas.datasets import TimeseriesDatasetResponse
from metadata_manager.models.schemas.dependencies import (
    DependentTimeSeriesMetadata,
    DependentTimeSeriesMetadataResponse,
)
from metadata_manager.models.schemas.sites import SiteMetadataResponse, SitesResponse

METADATA_CONNECTION = MetadataAPIManager(host=app_config.metadata_api_url, network="cosmos")


def load_config(
    config_type: Union[ComponentType, str], parameters: List[Tuple[str, str]]
) -> Optional[DataProcessingConfigurations]:
    """Load configuration data based on the given configuration type.

    Args:
        config_type: The type of configuration to load.
        parameters: API query parameters for the processing configuration endpoint.

    Returns:
        The parsed configurations.
    """
    if isinstance(config_type, str):
        config_type = ComponentType(config_type)

    config_mapping = {
        ComponentType.INFILLING: "infill-configuration",
        ComponentType.QUALITY_CONTROL: "qc",
        ComponentType.CORRECTION: "correction-configuration",
    }
    params = parameters + build_processing_config_type_query_parameter(config_mapping[config_type])
    data = asyncio.run(METADATA_CONNECTION.fetch_processing_configs(params))

    return DataProcessingConfigurations.model_validate(data)


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


def load_datasets(parameters: List[Tuple[str, str]]) -> TimeseriesDatasetResponse:
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


def load_sites() -> SitesResponse:
    """Validate and load the sites endpoint response.

    Returns:
        The parsed sites metadata.
    """
    data = asyncio.run(METADATA_CONNECTION.fetch_sites())
    return SitesResponse.model_validate(data)


def update_correction_configs_with_site_attributes(corr_configs: List[DataProcessingConfiguration]) -> Dict[str, Any]:
    """
    Update the correct configs with the values for any site parameters required.

    For example, if a correction config contains a site_parameter value of "ALTITUDE", the metadata for the site
    corresponding to the config will be fetched. The altitude value will be extracted and the "site_parameter" key value
    pair will be replaced with "altitude": altitude_value.

    Args:
        corr_configs: List of correction configuration objects.


    Returns:
        corr_configs: List of correction configuration objects with any site_attribute parameters replaced with the
            key value pairs for any required attributes.

    """
    for config in corr_configs:
        for config_item in config.configs:
            if config_item.parameters.get("site_attribute"):
                site_id = re.match(URI_ID_EXTRACT_REGEX, config.site_id).group(1)
                response = asyncio.run(METADATA_CONNECTION.fetch_site_metadata(site_id=site_id))
                site_metadata = SiteMetadataResponse.model_validate(response)

                # Replace the site attribute entry in the parameter dictionary with the corresponding key-value
                # pair for the attribute itself
                site_attribute_key = config_item.parameters["site_attribute"].lower()
                del config_item.parameters["site_attribute"]
                config_item.parameters[site_attribute_key] = site_metadata.get(site_attribute_key)

    return corr_configs

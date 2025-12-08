"""
Mapping functions to convert validated Pydantic API models into domain models.

These mappers extract the fields actually required by the pipeline and flatten nested metadata structures into simpler
domain-level objects.
"""

from datetime import datetime
from collections import defaultdict
from typing import Any

from new_processor.models.api_models.annotation import HasAnnotationItem
from new_processor.models.api_models.data_processing_configuration import (
    DataProcessingConfigurationItem,
)
from new_processor.models.api_models.dataset_timeseries import TimeSeriesDatasetItem
from new_processor.models.api_models.shared import ArgumentItem, HasCurrentConfigurationItem
from new_processor.models.api_models.site import SiteItem
from new_processor.models.domain_models.processing_config import MethodConfig, ProcessingConfig
from new_processor.models.domain_models.site_metadata import SiteMetadata
from new_processor.models.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import ConfigurationType, MethodType, ProcessingLevel
from new_processor.utils.strings import extract_uri_id


def map_dataset_item(item: TimeSeriesDatasetItem, network: str) -> TimeSeriesContainer:
    """Map a Pydantic TimeSeriesDatasetItem to a domain-level TimeSeriesContainer.

    Args:
        item: The validated Pydantic model representing a single dataset record.
        network: The network that this model belongs to TODO: Ideally this would be in the metadata API response

    Returns:
        A simplified TimeSeriesContainer domain model containing only the fields required for DAG construction and
        processing.
    """
    info = item.type[0]

    processing_level = ProcessingLevel(extract_uri_id(info.processing_level.id))
    variable = info.measure.variable.pref_label[0]
    source_site = extract_uri_id(item.originating_site[0].id)

    methodology = info.methodology
    method_config = methodology.configuration if methodology else None
    method_type = method_config.type.id if method_config else None
    method_current_config = method_config.has_current_configuration[0] if method_config else None
    method = method_current_config.method.id if method_current_config and method_current_config.method else None

    if method_type:
        method_type = MethodType(extract_uri_id(method_type))
    else:
        method_type = MethodType.LOAD

    depends_on = [d.id for d in item.depends_on]
    direct_depends_on = [d.id for d in item.direct_depends_on]

    return TimeSeriesContainer(
        ts_id=item.id,
        ref_id=info.id,
        network=network,
        resolution=info.measure.aggregation.resolution,
        periodicity=info.measure.aggregation.periodicity,
        processing_level=processing_level,
        variable=variable,
        source_bucket=item.source_bucket,
        source_dataset=item.source_dataset,
        source_column=item.source_column_name,
        source_site=source_site,
        method_type=method_type,
        method=method,
        depends_on=depends_on,
        direct_depends_on=direct_depends_on,
    )


def map_processing_config_item(
    item: DataProcessingConfigurationItem, all_site_metadata: dict[str, SiteMetadata]
) -> ProcessingConfig:
    """Map a DataProcessingConfigurationItem to a ProcessingConfig domain model.

    Some processing configurations will have "site_attribute" parameters that require fetching this metadata
    key from the site metadata.

    Args:
        item: The validated DataProcessingConfigurationItem from the API.
        all_site_metadata: Metadata for sites.

    Returns:
        A ProcessingConfig domain object containing annotations and a list of MethodConfig objects which provide
        specific method configurations for use in the processing pipeline
    """
    ts_id = item.applies_to_time_series[0].id
    site_id = item.applies_to_time_series[0].originating_site.id
    config_type = ConfigurationType(extract_uri_id(item.type.id))
    annotations = extract_annotations(item.has_annotation)

    site_metadata = all_site_metadata[site_id]

    method_configs = [map_method_config(cfg, site_metadata) for cfg in item.has_current_configuration or []]

    return ProcessingConfig(
        ts_id=ts_id,
        config_id=item.id,
        config_type=config_type,
        method_configs=method_configs,
        annotations=annotations,
    )


def map_method_config(current_config: HasCurrentConfigurationItem, site_metadata: SiteMetadata) -> MethodConfig:
    """Map a HasCurrentConfigurationItem into a MethodConfig domain model.

    Args:
        current_config: A single configuration definition for a method, possibly including an observation interval and
                        argument list.
        site_metadata: Metadata for the site this processing configuration applies to.

    Returns:
        A MethodConfig object describing a configuration of a processing method.
    """
    method = extract_uri_id(current_config.method.id)
    params = extract_arguments(current_config.argument, site_metadata)

    start_date, end_date = None, None
    if current_config.observation_interval:
        start_date = current_config.observation_interval.start_date
        end_date = current_config.observation_interval.end_date

    return MethodConfig(
        method=method,
        params=params,
        start_date=start_date,
        end_date=end_date,
    )


def extract_annotations(annotations: list[HasAnnotationItem]) -> dict[str, Any]:
    """Extract annotation key–value pairs from the configuration item.

    Args:
        annotations: A list of HasAnnotationItems taken from a DataProcessingConfigurationItem.

    Returns:
        A dictionary mapping annotation property identifiers to their values.
    """
    extracted = {}

    for ann in annotations:
        key = extract_uri_id(ann.property.id).replace("-", "_")
        if ann.has_value:
            extracted[key] = ann.has_value.value
        elif ann.has_value_series:
            extracted[key] = ann.has_value_series.has_current_value

    return extracted


def extract_arguments(argument_items: list[ArgumentItem], site_metadata: SiteMetadata) -> dict[str, Any]:
    """Extract method argument names and values from a configuration definition.

    Handles both direct literal values and references to other datasets.

    Args:
        argument_items: List of ArgumentItems from a HasCurrentConfigurationItem model.
        site_metadata: Metadata for the site this processing configuration applies to.

    Returns:
        A dictionary mapping parameter names to either literal values or referenced dataset identifiers. If a parameter
        appears multiple times, all values are preserved in a list.
    """
    collected_args = defaultdict(list)

    for arg in argument_items:
        param_name = extract_uri_id(arg.parameter.id).replace("-", "_")
        has_value = arg.has_value

        # Literal value
        if has_value.value is not None:
            # Resolve any special case where we need to extract parameter from the site metadata
            param_name, value = resolve_site_attribute(param_name, has_value.value, site_metadata)
            collected_args[param_name].append(value)

        # Reference value (dependent dataset)
        if has_value.value_reference is not None:
            ref_id = has_value.value_reference.id
            collected_args[param_name].append(ref_id)

    # Flatten singleton lists
    params = {k: vals[0] if len(vals) == 1 else vals for k, vals in collected_args.items()}
    return params


def resolve_site_attribute(param_name: str, value: str, site_metadata: SiteMetadata) -> tuple[str, Any]:
    """Resolve any special case where we need to extract parameter from the site metadata.

    Args:
        param_name: The name of the parameter to resolve.
        value: The value of the parameter.
        site_metadata: Metadata for the site this processing configuration applies to.

    Returns:
        Resolved parameter name and value.
    """
    if param_name.lower() != "site_attribute":
        return param_name, value

    actual_param = value.lower()
    actual_value = getattr(site_metadata, actual_param)
    return actual_param, actual_value


def map_site_metadata(item: SiteItem) -> SiteMetadata:
    """Map a Pydantic SiteItem to a domain-level SiteMetadata object.

    Args:
        item: The validated Pydantic model representing a single site.

    Returns:
        A simplified SiteMetadata domain model
    """
    start_date = datetime.fromisoformat(item.operating_period.start_date)
    end_date = datetime.fromisoformat(item.operating_period.end_date)

    return SiteMetadata(
        site_id=item.id,
        alt_id=item.identifier[0],
        full_name=item.label[0],
        easting=item.easting,
        northing=item.northing,
        lat=item.lat,
        lon=item.long,
        altitude=item.altitude,
        start_date=start_date,
        end_date=end_date,
    )

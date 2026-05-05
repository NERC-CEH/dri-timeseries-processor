"""
Mapping functions to convert validated Pydantic API models into domain models.

These mappers extract the fields actually required by the pipeline and flatten nested metadata structures into simpler
domain-level objects.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any

from dritimeseriesprocessor.models.api_models.annotation import HasAnnotationItem
from dritimeseriesprocessor.models.api_models.data_processing_configuration import (
    DataProcessingConfigurationItem,
)
from dritimeseriesprocessor.models.api_models.dataset_timeseries import TimeSeriesDatasetItem
from dritimeseriesprocessor.models.api_models.shared import ArgumentItem, HasCurrentValue, IDModel
from dritimeseriesprocessor.models.api_models.site import SiteItem
from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.utils.enums import ConfigurationType, ProcessingLevel
from dritimeseriesprocessor.utils.strings import extract_uri_id


def map_dataset_item(item: TimeSeriesDatasetItem, all_site_metadata: dict[str, SiteMetadata]) -> TimeSeriesContainer:
    """Map a Pydantic TimeSeriesDatasetItem to a domain-level TimeSeriesContainer.

    Args:
        item: The validated Pydantic model representing a single dataset record.
        all_site_metadata: Metadata for sites.

    Returns:
        A simplified TimeSeriesContainer domain model containing only the fields required for DAG construction and
        processing.
    """
    processing_level = ProcessingLevel(extract_uri_id(item.processing_level.id))
    metadata_site_id = item.originating_site[0].id

    source_site = extract_uri_id(metadata_site_id)
    source_network = extract_uri_id(item.originating_programme[0].id)

    source_site_identifier = all_site_metadata[metadata_site_id].alt_id

    return TimeSeriesContainer(
        ts_id=item.id,
        network=source_network,
        resolution=item.measure[0].aggregation.resolution,
        periodicity=item.measure[0].aggregation.periodicity,
        processing_level=processing_level,
        source_bucket=item.source_bucket,
        source_dataset=item.source_dataset,
        source_column=item.source_column_name,
        source_site=source_site,
        source_site_identifier=source_site_identifier,
        time_column_name=item.time_column_name,
    )


def map_processing_config_item(
    item: DataProcessingConfigurationItem, all_site_metadata: dict[str, SiteMetadata]
) -> DataProcessingConfig:
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
    ts_id = item.applies_to_dataset[0].id
    site_id = item.applies_to_dataset[0].originating_site[0].id
    config_type = ConfigurationType(extract_uri_id(item.type.id))
    annotations = extract_annotations(item.has_annotation)

    site_metadata = all_site_metadata[site_id]

    method_configs = [map_processing_method_config(cfg, site_metadata) for cfg in item.has_current_value or []]

    return DataProcessingConfig(
        ts_id=ts_id,
        config_id=item.id,
        config_type=config_type,
        method_configs=method_configs,
        annotations=annotations,
    )


def map_processing_method_config(
    current_config: HasCurrentValue, site_metadata: SiteMetadata
) -> DataProcessingMethodConfig:
    """Map an API response for a data processing method configuration into a domain model.

    Args:
        current_config: A single configuration definition for a method, possibly including an observation interval and
                        argument list.
        site_metadata: Metadata for the site this processing configuration applies to.

    Returns:
        A domain model object describing a configuration of a processing method.
    """
    method = extract_uri_id(current_config.method.id)
    params = extract_arguments(current_config.argument, site_metadata)

    start_date, end_date = None, None
    if current_config.observation_interval:
        start_date = current_config.observation_interval.start_date
        end_date = current_config.observation_interval.end_date

    return DataProcessingMethodConfig(
        method=method,
        params=params,
        start_date=start_date,
        end_date=end_date,
    )


def extract_annotations(annotations: list[HasAnnotationItem]) -> dict[str, Any] | None:
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
            extracted[key] = ann.has_value.value[0] if ann.has_value.value else ann.has_value.value_reference[0]
        elif ann.has_value_series:
            extracted[key] = ann.has_value_series.has_current_value

    return extracted


def extract_arguments(argument_items: list[ArgumentItem], site_metadata: SiteMetadata | None) -> dict[str, Any]:
    """Extract method argument names and values from a configuration definition.

    Handles both direct literal values and references to other datasets.

    Args:
        argument_items: List of ArgumentItems from a HasCurrentValue model.
        site_metadata: Metadata for the site this processing configuration applies to.

    Returns:
        A dictionary mapping parameter names to either literal values or referenced dataset identifiers. If a parameter
        appears multiple times, all values are preserved in a list.
    """
    collected_args = defaultdict(list)

    for arg in argument_items:
        param_name = extract_uri_id(arg.parameter.id).replace("-", "_")
        has_value = arg.has_value
        has_structured_value = arg.has_structured_value
        if has_value:
            # Literal value
            if has_value.value is not None:
                # Resolve any special case where we need to extract parameter from the site metadata
                # Annotations may have more than one value, site_attributes and other parameters have at most one.
                values = has_value.value  # Cannot set to lower here as not all values are strings
                if param_name == "annotation":
                    for param in values:
                        param_name = param.lower()
                        collected_args[param_name].append(site_metadata.annotations.get(param_name))
                else:
                    value = values[0]
                    if param_name == "site_attribute":
                        param_name = value.lower()
                        value = getattr(site_metadata, param_name)
                    collected_args[param_name].append(value)

            # Reference value (dependent dataset)
            if has_value.value_reference is not None:
                refs = has_value.value_reference
                if isinstance(refs, IDModel):
                    refs = [has_value.value_reference]
                for ref in refs:
                    collected_args[param_name].append(ref.id)

        if has_structured_value:
            # Extract any nested structured value arguments. This will be, used for example, for cases where we need
            # to extract deployment information for a sensor e.g. wind height for PE 30min
            structured_value_params = extract_arguments(has_structured_value.argument, site_metadata)
            collected_args[param_name].append(structured_value_params)

    # Flatten singleton lists
    params = {k: vals[0] if len(vals) == 1 else vals for k, vals in collected_args.items()}
    return params


def map_site_metadata(item: SiteItem) -> SiteMetadata:
    """Map a Pydantic SiteItem to a domain-level SiteMetadata object.

    Args:
        item: The validated Pydantic model representing a single site.

    Returns:
        A simplified SiteMetadata domain model
    """
    start_date = datetime.fromisoformat(item.operating_period.start_date)
    end_date = datetime.fromisoformat(item.operating_period.end_date) if item.operating_period.end_date else None

    alt_id = item.identifier[0] if item.identifier else None
    full_name = item.label[0] if item.label else None
    network = item.utilised_by[0].id if item.utilised_by else None
    annotations = extract_annotations(item.has_annotation) if item.has_annotation else None

    return SiteMetadata(
        site_id=item.id,
        network=network,
        alt_id=alt_id,
        full_name=full_name,
        easting=item.easting,
        northing=item.northing,
        lat=item.lat,
        lon=item.long,
        altitude=item.altitude,
        start_date=start_date,
        end_date=end_date,
        annotations=annotations,
    )

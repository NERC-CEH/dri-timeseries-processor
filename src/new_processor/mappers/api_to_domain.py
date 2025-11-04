"""
Mapping functions to convert validated Pydantic API models into domain models.

These mappers extract the fields actually required by the pipeline and flatten nested metadata structures into simpler
domain-level objects.
"""

from collections import defaultdict
from typing import Any

from src.new_processor.api_models.data_processing_configuration import (
    DataProcessingConfigurationItem,
)
from src.new_processor.api_models.dataset_timeseries import TimeSeriesDatasetItem
from src.new_processor.api_models.shared import HasCurrentConfigurationItem
from src.new_processor.domain_models.processing_config import MethodConfig, ProcessingConfig
from src.new_processor.domain_models.time_series_container import TimeSeriesContainer
from src.new_processor.utils.enums import ConfigurationType, MethodType, ProcessingLevel
from src.new_processor.utils.strings import extract_uri_id

from new_processor.api_models.annotation import HasAnnotationItem
from new_processor.api_models.shared import ArgumentItem


def map_dataset_item(item: TimeSeriesDatasetItem) -> TimeSeriesContainer:
    """Map a Pydantic TimeSeriesDatasetItem to a domain-level TimeSeriesContainer.

    Args:
        item: The validated Pydantic model representing a single dataset record.

    Returns:
        A simplified TimeSeriesContainer domain model containing only the fields required for DAG construction and
        processing.
    """
    info = item.type[0]

    processing_level = ProcessingLevel(extract_uri_id(info.processing_level.id))
    variable = info.measure.variable.pref_label[0]
    source_site = item.originating_site[0].id

    methodology = info.methodology
    method_config = methodology.configuration if methodology else None
    method_type = method_config.type.id if method_config else None
    method_current_config = method_config.has_current_configuration[0] if method_config else None
    method = method_current_config.method.id if method_current_config and method_current_config.method else None

    if method_type:
        method_type = MethodType(extract_uri_id(method_type))

    depends_on = [d.id for d in item.depends_on]
    direct_depends_on = [d.id for d in item.direct_depends_on]

    return TimeSeriesContainer(
        ts_id=item.id,
        ref_id=info.id,
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


def map_processing_config_item(item: DataProcessingConfigurationItem) -> ProcessingConfig:
    """Map a DataProcessingConfigurationItem to a ProcessingConfig domain model.

    Args:
        item: The validated DataProcessingConfigurationItem from the API.

    Returns:
        A ProcessingConfig domain object containing annotations and a list of MethodConfig objects which provide
        specific method configurations for use in the processing pipeline
    """
    config_type = ConfigurationType(extract_uri_id(item.type.id))
    annotations = extract_annotations(item.has_annotation)
    method_configs = [map_method_config(cfg) for cfg in item.has_current_configuration or []]

    return ProcessingConfig(
        config_id=item.id,
        config_type=config_type,
        method_configs=method_configs,
        annotations=annotations,
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


def map_method_config(current_config: HasCurrentConfigurationItem) -> MethodConfig:
    """Convert a HasCurrentConfigurationItem into a MethodConfig domain model.

    Args:
        current_config: A single configuration definition for a method, possibly including an observation interval and
                        argument list.

    Returns:
        A MethodConfig object describing a configuration of a processing method.
    """
    method = extract_uri_id(current_config.method.id)
    params = extract_arguments(current_config.argument)

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


def extract_arguments(argument_items: list[ArgumentItem]) -> dict[str, Any]:
    """Extract method argument names and values from a configuration definition.

    Handles both direct literal values and references to other datasets.

    Args:
        argument_items: List of ArgumentItems from a HasCurrentConfigurationItem model.

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
            collected_args[param_name].append(has_value.value)

        # Reference value (dependent dataset)
        if has_value.value_reference is not None:
            ref_id = has_value.value_reference.id
            collected_args[param_name].append(ref_id)

    # Flatten singleton lists
    params = {k: vals[0] if len(vals) == 1 else vals for k, vals in collected_args.items()}
    return params

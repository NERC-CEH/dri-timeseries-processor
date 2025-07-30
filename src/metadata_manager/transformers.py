"""Helpers to transform metadata API responses."""

import re
from typing import Dict, List, Union

from metadata_manager.models.common import SITE_ID_EXTRACT_REGEX, URI_ID_EXTRACT_REGEX
from metadata_manager.models.schemas.datasets import TimeseriesDatasetResponse
from metadata_manager.models.schemas.derivations import DerivationMetadata
from metadata_manager.models.schemas.sites import SitesResponse


def extract_cosmos_site_ids(site_metadata: SitesResponse) -> list:
    """Extract the COSMOS site ids from the validated response.

    Args:
        site_metadata: Validated site metadata from the sites endpoint.

    Returns:
        A list of sorted site ids.
    """
    sites = []

    for item in site_metadata.sites.site_list:
        match = re.search(r"cosmos-(\w+)$", item)
        if match:
            sites.append(match.group(1).upper())

    return sorted(sites)


def extract_site_ids(site_list: List[str], network: str) -> list:
    """Extract the site ids from the validated site_list.

    Args:
        site_list: Validated site list from the sites endpoint.
        network: The network

    Raises:
        Value Error if network not supported.
    Returns:
        A list of sorted site ids.
    """
    if network == "cosmos":
        return extract_cosmos_site_ids(site_list)
    else:
        raise ValueError(f"Network {network} not supported.")


def extract_timeseries_id_metadata(response: TimeseriesDatasetResponse) -> Dict[str, Dict[str, str]]:
    """Extract the metadata required for processing timeseries IDs from the dataset endpoint.
    Args:
        response: The TimeseriesDatasetResponse object from the metadata store dataset request.
    Returns:
        A dict of the required metadata for processing.
    """
    metadata = {}

    for item in response.items:
        ts_id_metadata = {}

        # Get the first type definition (assuming there's at least one)
        type_def = item.type[0] if item.type else None
        if not type_def:
            continue

        ts_id_metadata["ts_def"] = type_def.id
        ts_id_metadata["resolution"] = type_def.measure.aggregation.resolution
        ts_id_metadata["periodicity"] = type_def.measure.aggregation.periodicity

        # Extract processing level ID using regex
        ts_id_metadata["processing_level"] = re.match(URI_ID_EXTRACT_REGEX, type_def.processing_level.id).group(1)

        ts_id_metadata["sourceBucket"] = item.source_bucket
        ts_id_metadata["sourceDataset"] = item.source_dataset
        ts_id_metadata["sourceColumnName"] = item.source_column_name

        # Get the first originating site (assuming there's at least one)
        originating_site = item.originating_site[0] if item.originating_site else None
        if originating_site:
            ts_id_metadata["sourceSite"] = re.match(SITE_ID_EXTRACT_REGEX, originating_site.id).group(1).upper()

        metadata[item.id] = ts_id_metadata

    return metadata


def extract_timeseries_definition_metadata(
    derivation_metadata: DerivationMetadata,
) -> Dict[str, Dict[str, Union[str, List[str | None]]]]:
    """Extract the metadata required for deriving timeseries definitions.

    Args:
        derivation_metadata: The validated DerivationMetadata model from the response

    Returns:
        The required derivation metadata for processing.
    """
    metadata = {}

    if derivation_metadata.methodology:
        metadata["method_type"] = re.match(
            URI_ID_EXTRACT_REGEX, derivation_metadata.methodology.configuration_type
        ).group(1)
        if derivation_metadata.methodology.method:
            metadata["method"] = re.match(URI_ID_EXTRACT_REGEX, derivation_metadata.methodology.method).group(1)
        else:
            metadata["method"] = None
        metadata["inputs"] = derivation_metadata.methodology.uses

        if metadata["method_type"] == "process" and len(metadata["inputs"]) != 1:
            raise ValueError(
                f"Processed timeseries definition {derivation_metadata.timeseries_def} should have exactly one input."
            )

        if metadata["method_type"] in ("aggregate", "calculate") and not metadata["method"]:
            raise ValueError(f"Method type '{metadata['method_type']}' requires a method to be specified.")

    else:
        # If no methodology section then there will be no further dependencies
        metadata["inputs"] = []

    return metadata

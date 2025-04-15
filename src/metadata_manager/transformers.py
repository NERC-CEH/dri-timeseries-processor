"""Helpers to transform metadata API responses."""

import re
from typing import Any, Dict, List, Union

from metadata_manager.models.common import URI_ID_EXTRACT_REGEX, get_property
from metadata_manager.models.schemas.derivations import DerivationMetadata


def extract_cosmos_site_ids(response: Dict[str, Any]) -> list:
    """Extract the COSMOS site ids from the metadata store site request.

    Args:
        response: The response from the metadat store sites request.

    Returns:
        A list of sorted site ids.
    """
    sites = []

    for item in response["items"][0]["contains"]:
        match = re.search(r"cosmos-(\w+)$", item["@id"])
        if match:
            sites.append(match.group(1).upper())

    return sorted(sites)


def extract_site_ids(response: Dict[str, Any], network: str) -> list:
    """Extract the site ids from the metadata store site request.

    Args:
        response: The response from the metadata store sites request.

    Returns:
        A list of sorted site ids.
    """
    if network == "cosmos":
        return extract_cosmos_site_ids(response)
    else:
        raise ValueError(f"Network {network} not supported.")


def extract_timeseries_id_metadata(response: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Extract the metadata required for processing timeseries IDs from the dataset endpoint.

    Args:
        response: The response from the metadata store dataset request.

    Returns:
        A dict of the required metadata for processing.
    """
    metadata = {}
    for item in response["items"]:
        ts_id_metadata = {}

        ts_id_metadata["ts_def"] = get_property("@id", get_property("type", item))
        ts_id_metadata["resolution"] = get_property(
            "resolution", get_property("aggregation", get_property("measure", get_property("type", item)))
        )
        ts_id_metadata["periodicity"] = get_property(
            "periodicity", get_property("aggregation", get_property("measure", get_property("type", item)))
        )
        ts_id_metadata["sourceBucket"] = get_property("sourceBucket", item)
        ts_id_metadata["sourceDataset"] = get_property("sourceDataset", item)
        ts_id_metadata["sourceColumnName"] = get_property("sourceColumnName", item)
        ts_id_metadata["sourceSite"] = get_property("@id", get_property("originatingSite", item))

        metadata[get_property("@id", item)] = ts_id_metadata

    return metadata


def extract_timeseries_definition_metadata(
    derivation_metadata: DerivationMetadata,
) -> Dict[str, Union[Dict[str, Union[str, List[str | None]]]]]:
    """Extract the metadata required for deriving timeseries definitions.

    Args:
        derivation_metadata: The validated DerivationMetadata model from the response

    Returns:
        The required derivation metadata for processing.
    """
    metadata = {"methodology": {}}

    if derivation_metadata.methodology:
        metadata["methodology"]["method_type"] = re.match(
            URI_ID_EXTRACT_REGEX, derivation_metadata.methodology.configuration_type
        ).group(1)
        metadata["methodology"]["inputs"] = derivation_metadata.methodology.uses
    else:
        # If no methodology section then there will be no further dependencies
        metadata["methodology"]["inputs"] = []

    return metadata

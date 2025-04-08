"""Helpers to transform metadata API responses."""

import re
from typing import Any, Dict

from metadata_manager.models.common import get_property


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
            sites.append(match.group(1))

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


def extract_dataset_metadata(response: Dict[str, Any], key: str) -> list:
    """Extract the metadata required for processing timeseries from the dataset endpoint.

    Args:
        response: The response from the metadata store dataset request.
        key: What key the metadata is to be stored under.

    Returns:
        A list of the required metadata for processing.
    """
    processing_parameters = []
    for item in response["items"]:
        metadata = {key: {}}
        metadata["ts_id"] = get_property("@id", item)
        metadata["ts_def"] = get_property("@id", get_property("type", item))
        metadata[key]["resolution"] = get_property(
            "resolution", get_property("aggregation", get_property("measure", get_property("type", item)))
        )
        metadata[key]["periodicity"] = get_property(
            "periodicity", get_property("aggregation", get_property("measure", get_property("type", item)))
        )
        metadata[key]["sourceBucket"] = get_property("sourceBucket", item)
        metadata[key]["sourceDataset"] = get_property("sourceDataset", item)
        metadata[key]["sourceColumnName"] = get_property("sourceColumnName", item)
        metadata[key]["sourceSite"] = get_property("@id", get_property("originatingSite", item))

        processing_parameters.append(metadata)

    return processing_parameters

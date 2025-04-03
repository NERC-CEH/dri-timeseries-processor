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
            sites.append(match.group(1).lower())

    return sorted(sites)


def extract_site_ids(response: Dict[str, Any], network: str) -> list:
    """Extract the site ids from the metadata store site request.

    Args:
        response: The response from the metadat store sites request.

    Returns:
        A list of sorted site ids.
    """
    if network == "cosmos":
        return extract_cosmos_site_ids(response)
    else:
        raise ValueError(f"Network {network} not supported.")


def extract_dataset_metadata(response, type):
    processing_parameters = []
    for item in response['items']:
        metadata = {type: {}}
        metadata['ts_id'] = get_property("@id", item)
        metadata['ts_def'] = get_property("@id", get_property("type", item))
        metadata[type]['resolution'] = get_property('resolution', get_property('aggregation', get_property('measure', get_property('type', item))))
        metadata[type]['periodicity'] = get_property('periodicity', get_property('aggregation', get_property('measure', get_property('type', item))))
        metadata[type]['sourceBucket'] = get_property("sourceBucket", item)
        metadata[type]['sourceDataset'] = get_property("sourceDataset", item)
        metadata[type]['sourceColumnName'] = get_property("sourceColumnName", item)
        metadata[type]['sourceSite'] = get_property("@id", get_property("originatingSite", item)).rsplit("/")[-1]

        processing_parameters.append(metadata)

    return processing_parameters

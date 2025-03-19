"""Helpers to transform metadata API responses."""

import re
from typing import Any, Dict


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
        response: The response from the metadat store sites request.

    Returns:
        A list of sorted site ids.
    """
    if network == "cosmos":
        return extract_cosmos_site_ids(response)
    else:
        raise ValueError(f"Network {network} not supported.")

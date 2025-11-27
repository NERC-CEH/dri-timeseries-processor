"""
Common base URIs and endpoint constants used throughout the metadata API integration.
"""

from urllib.parse import urlparse

BASE_URI = "http://fdri.ceh.ac.uk"
REF_URI = f"{BASE_URI}/ref"
ID_URI = f"{BASE_URI}/id"
SITE_URI = f"{ID_URI}/site"

PROCESSING_LEVEL_URI = f"{REF_URI}/common/processing-level"
CONFIGURATION_TYPE_URI = f"{REF_URI}/common/configuration-type"


def remove_protocol_from_url(url: str) -> str:
    """Remove the protocol from a URL.

    Args:
        url: URL to remove protocol from

    Returns:
        URL with protocol removed

    Examples:
        >>> remove_protocol_from_url("https://www.example.com")
        "www.example.com"
    """
    endpoint_url = urlparse(url)
    # Remove the protocol scheme by setting it to an empty string
    endpoint_url = "".join(endpoint_url[1:])
    return endpoint_url

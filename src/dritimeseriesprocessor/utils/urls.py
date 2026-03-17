"""
Common base URIs and endpoint constants used throughout the metadata API integration.
"""

from urllib.parse import urlsplit

BASE_URI = "http://fdri.ceh.ac.uk"
REF_URI = f"{BASE_URI}/ref"
ID_URI = f"{BASE_URI}/id"
SITE_URI = f"{ID_URI}/site"
PLATFORM_URI = f"{ID_URI}/platform"
PROGRAMME_URI = f"{ID_URI}/programme"

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
    parts = urlsplit(url)

    # If no scheme, return unchanged
    if not parts.scheme:
        return url

    endpoint_url = parts.netloc + parts.path
    if parts.query:
        endpoint_url += f"?{parts.query}"
    if parts.fragment:
        endpoint_url += f"#{parts.fragment}"
    return endpoint_url

import isodate
from isodate import ISO8601Error
from urllib.parse import urlparse

import polars as pl


def validate_iso8601_duration(duration: str) -> bool:
    """
    Validate if the given string is a valid ISO 8601 duration.
    """
    try:
        isodate.parse_duration(duration)
        return True
    except ISO8601Error:
        return False


def remove_protocol_from_url(url: str) -> str:
    """ Remove the protocol from a URL.

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
    endpoint_url = ''.join(endpoint_url[1:])
    return endpoint_url

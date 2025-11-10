def extract_uri_id(uri: str) -> str:
    """Extract the final path segment from a URI.

    Args:
        uri: The URI to extract the final path segment from.

    Returns:
        The final path segment as a string.
    """
    if not isinstance(uri, str):
        raise ValueError(f"Input URI must be a string. Got: {type(uri)}")
    return uri.rstrip("/").split("/")[-1]

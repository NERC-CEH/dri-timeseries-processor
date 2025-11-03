def extract_uri_id(uri: str) -> str:
    """Extract the final path segment from a URI."""
    return uri.rstrip("/").split("/")[-1]

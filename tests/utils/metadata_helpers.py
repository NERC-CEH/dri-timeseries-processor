import hashlib
from urllib.parse import parse_qsl, urlparse

E2E_INPUT_BUCKET = "e2e-input"
E2E_OUTPUT_BUCKET = "e2e-output"


def stable_file_key(url: str) -> str:
    """Generate a stable key for a metadata API URL that can be used for cached filename.

    The key is derived from:
    - the URL path
    - all query parameters (sorted)

    Args:
        url: Full request URL, including any query parameters.

    Returns:
        A hexadecimal string suitable for use as a filename.
    """
    parsed = urlparse(url)
    path = parsed.path
    params = sorted(parse_qsl(parsed.query))

    if not params:
        params = []
    query = path + "&".join(f"{k}={v}" for k, v in params)

    # Replace characters that are problematic or ambiguous in filenames.
    for char in (" ", "/", "?", "&", "=", ":", "@"):
        query = query.replace(char, "_")

    # Turn the (what can be very long) url-based file key into a hash to use as the filename.
    return hash_key(query)


def hash_key(key: str, length: int = 20) -> str:
    """Hash a long key into a fixed-length identifier.

    Use the `hashlib.blake2b` hash type for consistent/persistent hashing across platforms

    Args:
        key: String to hash.
        length: Requested hash output length.

    Returns:
        Hexadecimal hash string of the requested length.
    """
    h = hashlib.blake2b(key.encode("utf-8"), digest_size=length)
    return h.hexdigest()

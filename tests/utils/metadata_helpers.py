import hashlib
from urllib.parse import urlparse, parse_qsl

from tests.utils.fixture_helpers import END_TO_END, load_json_file
from new_processor.utils.urls import SITE_URI

E2E_INPUT_BUCKET = "e2e-input"
E2E_OUTPUT_BUCKET = "e2e-output"


def stable_file_key(url):
    parsed = urlparse(url)
    path = parsed.path
    params = sorted(parse_qsl(parsed.query))

    if not params:
        params = []
    query = path + "&".join(f"{k}={v}" for k, v in params)
    chars = (" ", "/", "?", "&", "=", ":", "@")
    for char in chars:
        query = query.replace(char, "_")

    return hash_request(query)


def hash_request(file_key: str, length: int = 20) -> str:
    """ Turn the (what can be very long) url-based file key into a hash.

    Use the `hashlib.blake2b` hash type for consistent/persistent hashing across platforms
    """
    h = hashlib.blake2b(file_key.encode("utf-8"), digest_size=length)
    return h.hexdigest()

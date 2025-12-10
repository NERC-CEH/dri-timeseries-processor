"""
Local metadata loading functions.

Provides access to metadata files that are saved locally.
"""

import json
from functools import lru_cache

from new_processor import PACKAGE_ROOT
from new_processor.models.api_models.flags import CoreFlagResponse


def load_metadata_json(name: str) -> dict:
    """Load given metadata json file.

    Args:
        name: JSON file to load from local metadata directory

    Returns:
        Loaded JSON dict.
    """
    path = PACKAGE_ROOT / "__metadata__" / name
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def fetch_core_flags() -> CoreFlagResponse:
    """Fetch core flag metadata.

    In the future, this could move to the metadata API. For now, it loads from local JSON.

    Returns:
        The parsed core flag metadata.
    """
    data = load_metadata_json("core_flags.json")
    return CoreFlagResponse.model_validate(data)

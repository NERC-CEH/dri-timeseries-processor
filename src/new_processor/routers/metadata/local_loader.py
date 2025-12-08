"""
Local metadata loading functions.

Provides access to metadata files that are saved locally.
"""

import json
from functools import lru_cache

from new_processor import PACKAGE_ROOT
from new_processor.api_models.operations.flags import CoreFlagResponse
from new_processor.api_models.operations.operation import OperationRegistry
from new_processor.utils.enums import OperationType


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


@lru_cache(maxsize=1)
def fetch_methods(operation_type: OperationType) -> OperationRegistry:
    """Fetch method metadata for given operation type.

    Args:
        operation_type: Operation type to get method metadata for.

    Returns:
        The parsed method metadata.
    """
    mapping = {
        OperationType.QUALITY_CONTROL: "qc_methods.json",
        OperationType.INFILLING: "infilling_methods.json",
        OperationType.CORRECTION: "correction_methods.json",
    }

    filename = mapping.get(operation_type)
    if filename is None:
        raise ValueError(f"Unknown operation type {operation_type}")

    data = load_metadata_json(filename)
    return OperationRegistry.model_validate(data)

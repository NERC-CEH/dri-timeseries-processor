from typing import Any
from pydantic import BaseModel, field_validator
from new_processor.utils.enums import OperationType


class OperationDescriptor(BaseModel):
    """
    Metadata describing how to run a QC / Correction / Infill / Derivation (etc.) operation.
    """
    id: int
    name: str
    description: str
    function_name: str
    arg_mapping: dict[str, str] = {}
    kwargs: dict[str, Any] = {}

    @field_validator("id")
    def validate_id(cls, v):
        if v <= 0:
            raise ValueError("id must be positive")
        return v


class OperationRegistry(BaseModel):
    """
    A registry mapping operation names to their OperationDescriptor model.
    """
    operation_type: OperationType
    items: dict[str, OperationDescriptor]

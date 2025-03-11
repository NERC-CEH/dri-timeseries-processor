from typing import Dict

from pydantic import BaseModel, field_validator


class InfillingMethod(BaseModel):
    """Represents a specific infilling method.

    Attributes:
        method_id: Unique identifier for the method - should be a bitwise flag value.
        name: Human-readable name of the method
        description: Detailed description of what the method does
    """

    method_id: int
    name: str
    description: str

    @field_validator("method_id")
    @classmethod
    def validate_method_id(cls, method_id: int) -> int:
        """Validate method_id is positive."""
        if method_id <= 0:
            raise ValueError("method_id must be a positive integer")
        return method_id

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        """Validate name is not empty."""
        if not name.strip():
            raise ValueError("name cannot be empty")
        return name


class InfillingMethodRegistry(Dict[str, InfillingMethod]):
    """Registry of all infilling methods."""

    @classmethod
    def model_validate(cls, data: Dict[str, Dict]) -> "InfillingMethodRegistry":
        """Extract infilling method data.

        Args:
            data: Dictionary mapping method keys to method details

        Returns:
            Dictionary mapping method keys to Method objects
        """
        result = cls()

        for method_key, method_data in data.items():
            # Transform the method data to include the method_id from "id" field
            method_data["method_id"] = method_data.pop("id")

            # Create and validate the Method object
            method = InfillingMethod.model_validate(method_data)
            result[method_key] = method

        return result

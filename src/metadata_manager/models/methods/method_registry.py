from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, field_validator, model_validator

from dritimeseriesprocessor.infilling import methods as infilling_functions


class MethodType(Enum):
    INFILLING = "infilling"
    QC = "quality_control"


class Method(BaseModel):
    """Represents a specific method.

    Attributes:
        method_id: Unique identifier for the method - should be a bitwise flag value.
        method_type: Type of the method - e.g. Infill, QC.
        name: Human-readable name of the method
        description: Detailed description of what the method does
        function_name: Name of the function that runs the method
        arg_mapping: Mapping of function argument names to the property names from the metadata configuration
        arg_defaults: Default value to use for any of the function arguments
    """

    method_id: int
    method_type: MethodType
    name: str
    description: str
    function_name: str
    arg_mapping: dict = {}
    arg_defaults: dict = {}

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

    @model_validator(mode="before")
    @classmethod
    def extract_config_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract configuration information for configuration from raw JSON data.

        Args:
            data: Raw configuration data from the JSON.

        Returns:
            Processed configuration data.
        """
        result = {
            "method_id": data["id"],
            "method_type": MethodType(data["method_type"]),
            "name": data["name"],
            "description": data["description"],
            "function_name": data["function_name"],
            "arg_mapping": data.get("arg_mapping", {}),
            "arg_defaults": data.get("arg_defaults", {}),
        }
        return result

    def __call__(self, *args, **kwargs):
        """Call the method function directly.

        TODO: Only for infilling - temporary until qc-like refactor has been done.
        """
        if self.method_type == MethodType.INFILLING:
            module = infilling_functions

            func = getattr(module, self.function_name, None)
            if func is None:
                raise ValueError(f"Function '{self.function_name}' not found in module '{module}'")

            return func(*args, **kwargs)

        elif self.method_type == MethodType.QC:
            return None

        else:
            raise UserWarning(f"Unknown method type: {self.method_type}")


class InfillingMethods(Dict[str, Method]):
    """Registry of all infilling methods."""

    @classmethod
    def model_validate(cls, data: Dict[str, Dict]) -> "InfillingMethods":
        """Extract infilling method data.

        Args:
            data: Dictionary mapping method keys to method details

        Returns:
            Dictionary mapping method keys to Method objects
        """
        result = cls()

        for method_key, method_data in data.items():
            method_data["method_type"] = "infilling"
            result[method_key] = Method.model_validate(method_data)

        return result


class QcMethods(Dict[str, Method]):
    """Registry of all QC methods."""

    @classmethod
    def model_validate(cls, data: Dict[str, Dict]) -> "QcMethods":
        """Extract QC method data.

        Args:
            data: Dictionary mapping method keys to method details

        Returns:
            Dictionary mapping method keys to Method objects
        """
        result = cls()

        for method_key, method_data in data.items():
            method_data["method_type"] = "quality_control"
            result[method_key] = Method.model_validate(method_data)

        return result

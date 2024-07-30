"""
Config required for quality control.
This is a placeholder while a proper metadata store is being built.

The configs are built using dictionaries (update these when adding to them) and
validated with Pydantic.
Import qc_config from this file to have all verified config data in a single
object.
"""

from typing import Dict, List, Optional

from pydantic import (
    BaseModel,
    ValidationInfo,
    field_validator,
    model_validator,
)

from dritimeseriesprocessor.utils import validate_iso8601_duration

# Metadata on the available QC tests
qc_tests = [
    {
        "test_name": "RANGE",
        "description": "Checks if the value falls within a specified range.",
    },
    {
        "test_name": "TEST",
        "description": "Test test.",
    },
]

# Default min and max values for variables at different intervals
default_range_thresholds = [
    {
        "variable_name": "TA",
        "default": {
            "min_value": -30.0,
            "max_value": 55.0,
        },
    },
    {
        "variable_name": "PRECIP",
        "resolutions": {
            "PT1M": {
                "min_value": 0.0,
                "max_value": 10.0,
            },
            "PT30M": {
                "min_value": 0.0,
                "max_value": 100.0,
            },
        },
    },
]

# Mapping which variables should run which QC tests
variable_test_mapping = [
    {
        "variable_name": "TA",
        "tests": [
            "RANGE",
        ],
    },
    {
        "variable_name": "PRECIP",
        "tests": [
            "RANGE",
        ],
    },
]


def get_valid_qc_tests() -> List[str]:
    """
    Returns a list of valid QC test names.

    Returns:
        List[str]: A list of strings representing valid QC test names.
    """
    return [qc_test["test_name"] for qc_test in qc_tests]


class QCTest(BaseModel):
    """
    Represents a Quality Control test with its description.

    Attributes:
        description (str): A brief description of what the QC test checks.
    """

    test_name: str
    description: str


class RangeThreshold(BaseModel):
    """
    Defines the range of acceptable values for a variable.

    Attributes:
        min_value (float): The minimum acceptable value.
        max_value (float): The maximum acceptable value.

    Validators:
        check_max_greater_than_min: Ensures that max_value is greater than
        min_value.
    """

    min_value: float
    max_value: float

    @field_validator("max_value")
    def check_max_greater_than_min(cls, v: float, info: ValidationInfo) -> float:
        """
        Validates that the max_value is greater than min_value.

        Args:
            cls (Type[RangeThreshold]): The class of the model being validated.
            v (float): The value of max_value to validate.
            info (field_validator.Info): Information about the field being
            validated.

        Raises:
            ValueError: If max_value is not greater than min_value.

        Returns:
            float: The validated max_value.
        """
        if "min_value" in info.data and v < info.data["min_value"]:
            raise ValueError("max_value must be greater than min_value")
        return v


class VariableRangeThreshold(BaseModel):
    """
    Defines default or resolution-specific range thresholds for a variable.

    Attributes:
        default (Optional[RangeThreshold]): Default range thresholds for the
        variable.
        resolutions (Optional[Dict[str, RangeThreshold]]): Resolution-specific
        range thresholds.

    Validators:
        check_resolutions: Validates ISO 8601 duration keys in resolutions.
        check_mutually_exclusive: Ensures that either default or resolutions is
        provided, but not both.
    """

    variable_name: str
    default: Optional[RangeThreshold] = None
    resolutions: Optional[Dict[str, RangeThreshold]] = None

    @field_validator("resolutions")
    def check_resolutions(cls, v: Optional[Dict[str, RangeThreshold]]) -> Optional[Dict[str, RangeThreshold]]:
        """
        Validates ISO 8601 duration keys in the resolutions dictionary.

        Args:
            cls (Type[VariableRangeThreshold]): The class of the model being
            validated.
            v (Optional[Dict[str, RangeThreshold]]): The resolutions dictionary
            to validate.

        Raises:
            ValueError: If any key in resolutions is not a valid ISO 8601 duration.

        Returns:
            Optional[Dict[str, RangeThreshold]]: The validated resolutions dictionary.
        """
        if v:
            for key in v:
                if not validate_iso8601_duration(key):
                    raise ValueError(f"Invalid ISO 8601 duration: {key}")
        return v

    @model_validator(mode="after")
    def check_mutually_exclusive(
        cls, values: Dict[str, Optional[RangeThreshold]]
    ) -> Dict[str, Optional[RangeThreshold]]:
        """
        Ensures that either 'default' or 'resolutions' is provided, but not both.

        Args:
            cls (Type[VariableRangeThreshold]): The class of the model being
            validated.
            values (Dict[str, Optional[RangeThreshold]]): The values of the model.

        Raises:
            ValueError: If neither or both 'default' and 'resolutions' are provided.

        Returns:
            Dict[str, Optional[RangeThreshold]]: The validated values.
        """
        if values.default is None and values.resolutions is None:
            raise ValueError("Either 'default' or 'resolutions' must be provided")
        if values.default is not None and values.resolutions is not None:
            raise ValueError("Only one of 'default' or 'resolutions' can be " "provided, not both")
        return values


class VariableTestMapping(BaseModel):
    """
    Maps a variable to its associated QC tests.

    Attributes:
        variable_name (str): The name of the variable.
        tests (List[str]): A list of QC test names applicable to the variable.

    Validators:
        validate_tests: Ensures that all specified tests are valid QC tests.
    """

    variable_name: str
    tests: List[str]

    @field_validator("tests")
    def validate_tests(cls, v: List[str]) -> List[str]:
        """
        Validates that all specified tests are valid QC tests.

        Args:
            cls (Type[VariableTestMapping]): The class of the model being validated.
            v (List[str]): The list of tests to validate.
            info (field_validator.Info): Information about the field being validated.

        Raises:
            ValueError: If any test is not a valid QC test.

        Returns:
            List[str]: The validated list of tests.
        """
        valid_tests = get_valid_qc_tests()
        for test in v:
            if test not in valid_tests:
                raise ValueError(f"Test '{test}' is not a valid QC test")
        return v


class QCConfig(BaseModel):
    """
    Configurations for Quality Control.

    Attributes:
        qc_tests (Dict[str, QCTest]): A dictionary of QC tests.
        default_range_thresholds (Dict[str, VariableRangeThreshold]): Default
        range thresholds for variables.
        variable_test_mapping (Dict[str, List[str]]): Mapping of variables to QC
        tests.

    Instance:
        qc_config (QCConfig): An instance of QCConfig containing all verified
        config data.
    """

    qc_tests: List[QCTest]
    default_range_thresholds: List[VariableRangeThreshold]
    variable_test_mapping: List[VariableTestMapping]


# Instantiate the models
qc_config = QCConfig(
    qc_tests=[QCTest(**qc_test) for qc_test in qc_tests],
    default_range_thresholds=[VariableRangeThreshold(**range_thresh) for range_thresh in default_range_thresholds],
    variable_test_mapping=[VariableTestMapping(**var_test_map) for var_test_map in variable_test_mapping],
)

"""
Config required for quality control.
This is a placeholder while a proper metadata store is being built.

The configs are built using dictionaries (update these when adding to them) and
validated with Pydantic.
Import qc_config from this file to have all verified config data in a single
object.
"""

from typing import List, Optional, Union

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
        "test_name": "BATTV",
        "description": "Checks if battery voltage is too low.",
    },
]

# Range test - Min and max values for variables.
var_range_thresholds = [
    {
        "variable_id": "TA",
        "defaults": [
            {
                "min_value": -30.0,
                "max_value": 55.0,
            },
        ],
        "sites": [
            {
                "site_id": "BUNNY",
                "resolutions": ["PT1M", "PT15M", "PT30M"],
                "min_value": -25.0,
                "max_value": 50.0,
            },
        ],
    },
    {
        "variable_id": "PRECIP",
        "defaults": [
            {
                "resolutions": ["PT1M"],
                "min_value": 0.0,
                "max_value": 10.0,
            },
            {
                "resolutions": ["PT15M"],
                "min_value": 0.0,
                "max_value": 60.0,
            },
            {
                "resolutions": ["PT30M"],
                "min_value": 0.0,
                "max_value": 100.0,
            },
        ],
        "sites": [
            {
                "site_id": "BUNNY",
                "resolutions": ["PT30M"],
                "min_value": 0.0,
                "max_value": 90.0,
            },
        ],
    },
]


# Battery test - Min acceptable voltage
battery_voltage_threshold = 10

# Soilmet scan test - min acceptable number of scans
soilmet_scan_threshold = 

# Mapping which variables should run which QC tests
variable_test_mapping = [
    {
        "variable_id": "TA",
        "tests": [
            "RANGE",
            "BATTV",
        ],
    },
    {
        "variable_id": "PRECIP",
        "tests": [
            "RANGE",
            "BATTV",
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

    site_id: Optional[str] = None
    resolutions: Optional[List[str]] = None
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

    @field_validator("resolutions")
    def check_resolutions(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """
        Validates ISO 8601 duration keys in the resolutions list.

        Args:
            cls (Type[RangeThreshold]): The class of the model being
            validated.
            v (Optional[Lust[str]]): The resolutions list to validate.

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


class VariableRangeThresholds(BaseModel):
    """
    Defines the range thresholds for a variable, including default and site-specific thresholds.

    Attributes:
        variable_id (str): The identifier for the variable.
        defaults (List[RangeThreshold]): List of default range thresholds for the variable.
        sites (Optional[List[RangeThreshold]]): List of site-specific range thresholds for the variable.

    Validators:
        check_site_id_in_sites: Ensures that every RangeThreshold in 'sites' contains a 'site_id'.
    """

    variable_id: str
    defaults: List[RangeThreshold]
    sites: Optional[List[RangeThreshold]] = None

    @model_validator(mode="after")
    def check_site_id_in_sites(cls, values: "VariableRangeThresholds") -> "VariableRangeThresholds":
        """
        Ensures that every RangeThreshold in 'sites' contains a 'site_id'.

        Args:
            cls (Type[VariableRangeThresholds]): The class of the model being validated.
            values (VariableRangeThresholds): The instance of the model.

        Raises:
            ValueError: If any RangeThreshold in 'sites' does not contain a 'site_id'.

        Returns:
            VariableRangeThresholds: The validated instance.
        """
        if values.sites:
            for site in values.sites:
                if not site.site_id:
                    raise ValueError("Each RangeThreshold in 'sites' must contain a 'site_id'")
        return values


class ValueThreshold(BaseModel):
    """
    Defines a threshold value for a variable.

    Attributes:
        threshold (float): The threshold value.

    """

    threshold: float


class VariableTestMapping(BaseModel):
    """
    Maps a variable to its associated QC tests.

    Attributes:
        variable_id (str): The name of the variable.
        tests (List[str]): A list of QC test names applicable to the variable.

    Validators:
        validate_tests: Ensures that all specified tests are valid QC tests.
    """

    variable_id: str
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
        var_range_thresholds (Dict[str, RangeThreshold]): Range thresholds for variables.
        variable_test_mapping (Dict[str, List[str]]): Mapping of variables to QC
        tests.

    Instance:
        qc_config (QCConfig): An instance of QCConfig containing all verified
        config data.
    """

    qc_tests: List[QCTest]
    var_range_thresholds: List[VariableRangeThresholds]
    variable_test_mapping: List[VariableTestMapping]
    battv_threshold: ValueThreshold


def get_qc_config(
    config: str = "all",
) -> Union[QCConfig, List[Union[QCTest, VariableRangeThresholds, VariableTestMapping]]]:
    """
    Retrieve Quality Control (QC) configuration based on the specified config type.

    This function returns different QC configuration objects or lists depending on the
    input parameter. It uses predefined lists (qc_tests, var_range_thresholds,
    variable_test_mapping) to create the configuration.

    Args:
        config (str, optional): The type of configuration to retrieve.
            Possible values are:
            - "all": Returns a QCConfig object with all configurations.
            - "tests": Returns a list of QCTest objects.
            - "range_thresholds": Returns a list of VariableRangeThresholds objects.
            - "variable_test_map": Returns a list of VariableTestMapping objects.
            - "battv_threshold": Returns battery voltage ValueThreshold object.
            Defaults to "all".

    Returns:
        Union[QCConfig, List[Union[QCTest, VariableRangeThresholds, VariableTestMapping, ValueThreshold]]]:
            The requested QC configuration.

    Raises:
        ValueError: If an invalid config type is provided.
    """
    if config == "all":
        qc_config = QCConfig(
            qc_tests=[QCTest(**qc_test) for qc_test in qc_tests],
            var_range_thresholds=[VariableRangeThresholds(**thresh_dict) for thresh_dict in var_range_thresholds],
            variable_test_mapping=[VariableTestMapping(**var_test_map) for var_test_map in variable_test_mapping],
            battv_threshold=ValueThreshold(threshold=battery_voltage_threshold),
        )
    elif config == "tests":
        qc_config = [QCTest(**qc_test) for qc_test in qc_tests]
    elif config == "range_thresholds":
        qc_config = [VariableRangeThresholds(**thresh_dict) for thresh_dict in var_range_thresholds]
    elif config == "variable_test_map":
        qc_config = [VariableTestMapping(**var_test_map) for var_test_map in variable_test_mapping]
    elif config == "battv_threshold":
        qc_config = ValueThreshold(threshold=battery_voltage_threshold)
    else:
        raise ValueError("Not a valid config type")

    return qc_config

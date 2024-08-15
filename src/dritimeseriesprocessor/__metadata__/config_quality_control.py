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

# Metadata on the QC tests and which variables to run.
qc_tests = {
    "RANGE": {
        "test_name": "Range test",
        "description": "Checks if the value falls within a specified range.",
        "variables": [
            "TA",
            "PRECIP",
        ],
    },
    "BATTV": {
        "test_name": "Battery voltage test",
        "description": "Checks if battery voltage is too low.",
        "variables": [
            "TA",
            "PRECIP",
        ],
    },
    "SCANS": {
        "test_name": "Soilmet scans check",
        "description": "Checks if the number of SOILMET scans/samples are too low.",
        "variables": [
            "CTS_BARE",
            "CTS_MOD",
            "CTS_MOD2",
            "CTS_SNOW",
            "G1",
            "G2",
            "LWIN",
            "LWOUT",
            "PA",
            "Q",
            "RH",
            "SNOWD_DISTANCE_UNC",
            "STP_TSOIL2",
            "STP_TSOIL5",
            "STP_TSOIL10",
            "STP_TSOIL20",
            "STP_TSOIL50",
            "SWIN",
            "SWOUT",
            "TA",
            "WD",
            "WS",
        ],
    },
    "ERROR_CODES": {
        "test_name": "Error codes qc check",
        "description": "Check for specific error codes",
        "variables": [
            "WS",
            "COV_TS_UY",
            "CTS_MOD",
            "G2",
            "HS",
            "LWOUT",
            "RHO_A_MEAN",
            "SWOUT",
            "TDT4_TSOIL",
            "TDT4_VWC",
            "TDT5_SOILEC",
            "TDT7_VWC",
            "TDT8_VWC",
            "TDT9_SOILEC",
            "COV_UX_UY",
            "LWIN",
            "PROFILE_SOILEC15",
            "PROFILE_VWC15"
        ]
    }
}

# Range test - Min and max values for variables.
var_range_thresholds = {
    "TA": {
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
    "PRECIP": {
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
}

# Threshold values could be moved to a structure like the range
# thresholds if complexity increases
# Battery test - Min acceptable voltage
battery_voltage_threshold = 10.0

# Soilmet scan test - min acceptable number of scans
soilmet_scan_threshold = 60.0


class QCTest(BaseModel):
    """
    Info on a QC test including which variables it should run.

    Attributes:
        test_name (str): The name of the test
        description (str): Description of the test
        variables (List[str]): A list of variables applicable to run the test.
    """

    test_name: str
    description: str
    variables: List[str]


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
        variable (str): The identifier for the variable.
        defaults (List[RangeThreshold]): List of default range thresholds for the variable.
        sites (Optional[List[RangeThreshold]]): List of site-specific range thresholds for the variable.

    Validators:
        check_site_id_in_sites: Ensures that every RangeThreshold in 'sites' contains a 'site_id'.
    """

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


def get_qc_config(config: str) -> Union[List[Union[QCTest, VariableRangeThresholds]]]:
    """
    Retrieve Quality Control (QC) configuration based on the specified config type.

    This function returns different QC configuration objects depending on the
    input parameter.

    Args:
        config (str): The type of configuration to retrieve.
            Possible values are:
            - "qc_tests": Returns a list of QCTest objects.
            - "range_thresholds": Returns a list of VariableRangeThresholds objects.
            - "battv_threshold": Returns battery voltage ValueThreshold object.
            - "soilmet_scan_threshold": Returns soilmet scan ValueThreshold value.
            Defaults to "all".

    Returns:
        Union[List[Union[VariableRangeThresholds, QCTest, ValueThreshold]]]:
            The requested QC configuration.

    Raises:
        ValueError: If an invalid config type is provided.
    """
    if config == "qc_tests":
        qc_config = {test: QCTest(**info) for test, info in qc_tests.items()}
    elif config == "range_thresholds":
        qc_config = {var: VariableRangeThresholds(**thresh_dict) for var, thresh_dict in var_range_thresholds.items()}
    elif config == "battv_threshold":
        qc_config = ValueThreshold(threshold=battery_voltage_threshold)
    elif config == "soilmet_scan_threshold":
        qc_config = ValueThreshold(threshold=soilmet_scan_threshold)
    else:
        raise ValueError("Not a valid config type")

    return qc_config

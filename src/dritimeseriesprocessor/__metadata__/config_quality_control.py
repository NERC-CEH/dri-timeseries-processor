"""
Config required for quality control.
This is a placeholder while a proper metadata store is being built.

The configs are built using dictionaries (update these when adding to them) and
validated with Pydantic.
Import qc_config from this file to have all verified config data in a single
object.
"""

import json
from pathlib import Path
from typing import List, Optional, Union

from pydantic import (
    BaseModel,
    ValidationInfo,
    field_validator,
    model_validator,
)

from dritimeseriesprocessor.utils import validate_iso8601_duration


class QCTest(BaseModel):
    """
    Info on a QC test including which variables it should run.

    Attributes:
        test_name (str): The name of the test
        description (str): Description of the test
        variables (List[str]): A list of variables applicable to run the test.
        id (int): Flag ID value used to flag rows that fail the test
    """

    test_name: str
    description: str
    variables: List[str]
    id: int


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


class SpikeThreshold(BaseModel):
    """
    Defines the range of acceptable values for a variable.

    Attributes:
        threshold (float): The minimum acceptable value to constitute a spike.
    """

    site_id: Optional[str] = None
    resolutions: Optional[List[str]] = None
    threshold: float


class VariableSpikeThresholds(BaseModel):
    """Defines the spike thresholds for a variable, including default and site-specific thresholds.

    Attributes:
        variable (str): The identifier for the variable.
        defaults (List[RangeThreshold]): List of default range thresholds for the variable.
        sites (Optional[List[RangeThreshold]]): List of site-specific range thresholds for the variable.

    Validators:
        check_site_id_in_sites: Ensures that every SpikeThreshold in 'sites' contains a 'site_id'.
    """

    defaults: List[SpikeThreshold]
    sites: Optional[List[SpikeThreshold]] = None

    @model_validator(mode="after")
    def check_site_id_in_sites(cls, values: "VariableSpikeThresholds") -> "VariableSpikeThresholds":
        if values.sites:
            for site in values.sites:
                if not site.site_id:
                    raise ValueError("Each SpikeThreshold in 'sites' must contain a 'site_id'")
        return values


def get_qc_config(config: str) -> Union[dict, ValueThreshold]:
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
            - "spike_thresholds": Returns a list of VariableThresholds objects.

    Returns:
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
    elif config == "spike_thresholds":
        qc_config = {var: VariableSpikeThresholds(**thresh_dict) for var, thresh_dict in var_spike_thresholds.items()}
    else:
        raise ValueError("Not a valid config type")

    return qc_config


# Instantiate the models
with open(Path(__file__).parent / "config_files" / "quality_control.json", "r") as f:
    content = json.load(f)

    qc_tests = content["qc_tests"]
    var_range_thresholds = content["var_range_thresholds"]
    battery_voltage_threshold = content["battery_voltage_threshold"]
    soilmet_scan_threshold = content["soilmet_scan_threshold"]
    var_spike_thresholds = content["var_spike_thresholds"]

    del content

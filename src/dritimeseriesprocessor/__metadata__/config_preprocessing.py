"""
Config required for preprocessing.
This is a placeholder while a proper metadata store is being built.

The configs are built using dictionaries (update these when adding to them) and
validated with Pydantic.
Import preprocessing_config from this file to have all verified config data in
a single object.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import (
    BaseModel,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


def get_valid_method_ids() -> list:
    """
    Retrieve a list of valid method IDs from the correction methods data.

    Returns:
        list: A list of valid METHOD_IDs.
    """
    return [method["METHOD_ID"] for method in correction_methods_data]


class CorrectionMethod(BaseModel):
    """
    A model representing a correction method.

    Attributes:
        METHOD_ID (str): The identifier for the correction method.
        DESCRIPTION (str): A description of the correction method.
    """

    METHOD_ID: str
    DESCRIPTION: str


class Correction(BaseModel):
    """
    A model representing a correction to be applied.

    Attributes:
        SITE_ID (str): The site identifier where the correction applies.
        VARIABLE (str): The variable to be corrected.
        START_DATETIME (datetime): The start date and time for the correction.
        END_DATETIME (Optional[datetime]): The end date and time for the correction.
        METHOD_ID (str): The method identifier for the correction.
        CORRECTION_FACTOR (Optional[float]): The factor by which to correct.
        DESCRIPTION (str): A description of the correction.
    """

    SITE_ID: str
    VARIABLE: str
    START_DATETIME: datetime
    END_DATETIME: Optional[datetime] = None
    METHOD_ID: str = Field(..., validate_default=True)
    CORRECTION_FACTOR: Optional[float] = None
    DESCRIPTION: str

    @field_validator("METHOD_ID")
    @classmethod
    def validate_method_id(cls, v: str) -> str:
        """
        Validate that the METHOD_ID is one of the valid method IDs.

        Args:
            v (str): The METHOD_ID to validate.

        Returns:
            str: The validated METHOD_ID.

        Raises:
            ValueError: If the METHOD_ID is not valid.
        """
        valid_methods = get_valid_method_ids()
        if v not in valid_methods:
            raise ValueError(f"Invalid METHOD_ID: {v}. Must be one of {valid_methods}")
        return v

    @field_validator("END_DATETIME")
    @classmethod
    def end_datetime_must_be_after_start(cls, v: Optional[datetime], info: ValidationInfo) -> datetime:
        """
        Validate that END_DATETIME is after START_DATETIME if it is provided.

        Args:
            v (Optional[datetime]): The END_DATETIME to validate.
            info (ValidationInfo): The validation information context.

        Returns:
            datetime: The validated END_DATETIME.

        Raises:
            ValueError: If END_DATETIME is before START_DATETIME.
        """
        if v is not None:
            start_datetime = info.data.get("START_DATETIME")
            if start_datetime and v < start_datetime:
                raise ValueError("END_DATETIME must be after START_DATETIME")
        return v

    @model_validator(mode="after")
    def check_method_variable(cls, values: "Correction") -> "Correction":
        """
        Validate that the METHOD_ID is consistent with the VARIABLE.

        Args:
            values (Correction): The Correction instance to validate.

        Returns:
            Correction: The validated Correction instance.

        Raises:
            ValueError: If METHOD_ID is inconsistent with VARIABLE.
        """
        method_id = values.METHOD_ID
        variable = values.VARIABLE

        if method_id == "LW_CORR" and variable not in ["LWIN", "LWOUT"]:
            raise ValueError('If METHOD_ID is "LW_CORR", VARIABLE must be either "LWIN" or "LWOUT"')
        if method_id == "PA_CORR" and variable != "PA":
            raise ValueError('If METHOD_ID is "PA_CORR", VARIABLE must be "PA"')
        if method_id == "WD_CORR" and variable != "WD":
            raise ValueError('If METHOD_ID is "WD_CORR", VARIABLE must be "WD"')

        return values


class PreprocessingConfig(BaseModel):
    """
    A model representing the preprocessing configuration.

    Attributes:
        correction_methods (List[CorrectionMethod]): A list of correction methods.
        corrections (List[Correction]): A list of corrections to be applied.
    """

    correction_methods: List[CorrectionMethod]
    corrections: List[Correction]


# Instantiate the models
with open(Path(__file__).parent / "config_files" / "corrections.json", "r") as f:
    content = json.load(f)

    correction_methods_data = content["methods"]
    corrections_data = content["data"]

    preprocessing_config = PreprocessingConfig(correction_methods=correction_methods_data, corrections=corrections_data)

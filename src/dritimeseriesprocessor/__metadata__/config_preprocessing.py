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
        list: A list of valid method_ids.
    """
    return [method["method_id"] for method in correction_methods_data]


class CorrectionMethod(BaseModel):
    """
    A model representing a correction method.

    Attributes:
        method_id (str): The identifier for the correction method.
        description (str): A description of the correction method.
    """

    method_id: str
    description: str
    id: int


class Correction(BaseModel):
    """
    A model representing a correction to be applied.

    Attributes:
        site_id (str): The site identifier where the correction applies.
        variable (str): The variable to be corrected.
        start_datetime (datetime): The start date and time for the correction.
        end_datetime (Optional[datetime]): The end date and time for the correction.
        method_id (str): The method identifier for the correction.
        correction_factor (Optional[float]): The factor by which to correct.
        description (str): A description of the correction.
    """

    site_id: str
    variable: str
    start_datetime: datetime
    end_datetime: Optional[datetime] = None
    method_id: str = Field(..., validate_default=True)
    correction_factor: Optional[float] = None
    description: str

    @field_validator("method_id")
    @classmethod
    def validate_method_id(cls, v: str) -> str:
        """
        Validate that the method_id is one of the valid method IDs.

        Args:
            v (str): The method_id to validate.

        Returns:
            str: The validated method_id.

        Raises:
            ValueError: If the method_id is not valid.
        """
        valid_methods = get_valid_method_ids()
        if v not in valid_methods:
            raise ValueError(f"Invalid method_id: {v}. Must be one of {valid_methods}")
        return v

    @field_validator("end_datetime")
    @classmethod
    def end_datetime_must_be_after_start(cls, v: Optional[datetime], info: ValidationInfo) -> datetime:
        """
        Validate that end_datetime is after start_datetime if it is provided.

        Args:
            v (Optional[datetime]): The end_datetime to validate.
            info (ValidationInfo): The validation information context.

        Returns:
            datetime: The validated end_datetime.

        Raises:
            ValueError: If end_datetime is before start_datetime.
        """
        if v is not None:
            start_datetime = info.data.get("start_datetime")
            if start_datetime and v < start_datetime:
                raise ValueError("end_datetime must be after start_datetime")
        return v

    @model_validator(mode="after")
    def check_method_variable(cls, values: "Correction") -> "Correction":
        """
        Validate that the method_id is consistent with the variable.

        Args:
            values (Correction): The Correction instance to validate.

        Returns:
            Correction: The validated Correction instance.

        Raises:
            ValueError: If method_id is inconsistent with variable.
        """
        method_id = values.method_id
        variable = values.variable

        if method_id == "LW_CORR" and variable not in ["LWIN", "LWOUT"]:
            raise ValueError('If method_id is "LW_CORR", variable must be either "LWIN" or "LWOUT"')
        if method_id == "PA_CORR" and variable != "PA":
            raise ValueError('If method_id is "PA_CORR", variable must be "PA"')
        if method_id == "WD_CORR" and variable != "WD":
            raise ValueError('If method_id is "WD_CORR", variable must be "WD"')

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

    del content

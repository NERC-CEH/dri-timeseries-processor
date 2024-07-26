"""
Config required for preprocessing.
This is a placeholder while a proper metadata store is being built.

The configs are built using dictionaries (update these when adding to them) and
validated with Pydantic.
Import preprocessing_config from this file to have all verified config data in
a single object.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import (
    BaseModel,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

correction_methods_data = [
    {
        "METHOD_ID": "ADD",
        "DESCRIPTION": "Sum the data point and correction value. E.g. "
        "y=x+ C, where x is the data point and C is the change factor.",
    },
    {
        "METHOD_ID": "LW_CORR",
        "DESCRIPTION": "Correction for long wave radiation where calibration " "values are incorrect.",
    },
    {
        "METHOD_ID": "MULTIPLY",
        "DESCRIPTION": "Multiply the data point by a correction factor. E.g. "
        "y=Cx where x is the data point and C is the correction factor.",
    },
    {
        "METHOD_ID": "PA_CORR",
        "DESCRIPTION": "Correction for pressure where adjust has been " "calculated from mean sea level pressure.",
    },
    {
        "METHOD_ID": "POWER",
        "DESCRIPTION": "Raise the data point to a power. E.g. y=x^C, x is "
        "the data point and C is the change factor.",
    },
    {
        "METHOD_ID": "WD_CORR",
        "DESCRIPTION": "Correction for wind direction orientation.",
    },
]

corrections_data = [
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "SWOUT",
        "START_DATETIME": "2016-07-28T15:00:00",
        "END_DATETIME": "2018-12-20T12:30:00",
        "CORRECTION_FACTOR": 1.00644,
        "DESCRIPTION": "Short wave radiation correction",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "LWIN",
        "START_DATETIME": "2016-07-28T15:00:00",
        "END_DATETIME": "2018-12-20T12:30:00",
        "CORRECTION_FACTOR": 0.02559,
        "DESCRIPTION": "Long wave radiation correction",
        "METHOD_ID": "LW_CORR",
    },
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "LWOUT",
        "START_DATETIME": "2016-07-28T15:00:00",
        "END_DATETIME": "2018-12-20T12:30:00",
        "CORRECTION_FACTOR": 1.0337,
        "DESCRIPTION": "Long wave radiation correction",
        "METHOD_ID": "LW_CORR",
    },
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "G1",
        "START_DATETIME": "2016-07-28T14:00:00",
        "END_DATETIME": "2016-07-29T00:00:00",
        "CORRECTION_FACTOR": 0.1986,
        "DESCRIPTION": "Heat flux plate correction",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "G1",
        "START_DATETIME": "2016-08-01T10:30:00",
        "END_DATETIME": "2016-08-02T00:00:00",
        "CORRECTION_FACTOR": 0.1986,
        "DESCRIPTION": "Heat flux plate correction",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "G1",
        "START_DATETIME": "2016-08-02T10:00:00",
        "END_DATETIME": "2016-08-03T00:00:00",
        "CORRECTION_FACTOR": 0.1986,
        "DESCRIPTION": "Heat flux plate correction",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "G1",
        "START_DATETIME": "2016-08-17T00:30:00",
        "END_DATETIME": "2016-08-18T00:00:00",
        "CORRECTION_FACTOR": 0.1986,
        "DESCRIPTION": "Heat flux plate correction",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "G1",
        "START_DATETIME": "2016-08-20T06:30:00",
        "END_DATETIME": "2016-08-21T00:00:00",
        "CORRECTION_FACTOR": 0.1986,
        "DESCRIPTION": "Heat flux plate correction",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "G1",
        "START_DATETIME": "2016-08-21T01:30:00",
        "END_DATETIME": "2016-08-22T00:00:00",
        "CORRECTION_FACTOR": 0.1986,
        "DESCRIPTION": "Heat flux plate correction",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "SPENF",
        "VARIABLE": "SWIN",
        "START_DATETIME": "2020-07-15T14:00:00",
        "END_DATETIME": "2020-07-17T12:00:00",
        "CORRECTION_FACTOR": 0.99245,
        "DESCRIPTION": "Short wave radiation correction",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "SPENF",
        "VARIABLE": "SWOUT",
        "START_DATETIME": "2020-07-15T14:00:00",
        "END_DATETIME": "2020-07-17T12:00:00",
        "CORRECTION_FACTOR": 1.03832,
        "DESCRIPTION": "Short wave radiation correction",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "SPENF",
        "VARIABLE": "LWOUT",
        "START_DATETIME": "2020-07-15T14:00:00",
        "END_DATETIME": "2020-07-17T12:00:00",
        "CORRECTION_FACTOR": 0.84191,
        "DESCRIPTION": "Long wave radiation correction",
        "METHOD_ID": "LW_CORR",
    },
    {
        "SITE_ID": "HOLLN",
        "VARIABLE": "PA",
        "START_DATETIME": "2022-03-01T00:30:00",
        "END_DATETIME": "2022-04-01T00:00:00",
        "CORRECTION_FACTOR": -3.7,
        "DESCRIPTION": "Pressure correction from MSLP bias",
        "METHOD_ID": "PA_CORR",
    },
    {
        "SITE_ID": "HOLLN",
        "VARIABLE": "PA",
        "START_DATETIME": "2022-04-01T00:30:00",
        "END_DATETIME": "2022-05-03T14:00:00",
        "CORRECTION_FACTOR": -2.8,
        "DESCRIPTION": "Pressure correction from MSLP bias",
        "METHOD_ID": "PA_CORR",
    },
    {
        "SITE_ID": "FINCH",
        "VARIABLE": "WD",
        "START_DATETIME": "2017-06-07T11:30:00",
        "END_DATETIME": None,
        "CORRECTION_FACTOR": None,
        "DESCRIPTION": "Wind direction orientation calculated incorrectly in program",
        "METHOD_ID": "WD_CORR",
    },
    {
        "SITE_ID": "CHOBH",
        "VARIABLE": "PRECIP",
        "START_DATETIME": "2016-05-10T13:30:00",
        "END_DATETIME": "2016-05-11T12:30:00",
        "CORRECTION_FACTOR": 0.16667,
        "DESCRIPTION": "Precip x6 too large",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "CHIMN",
        "VARIABLE": "CTS_MOD",
        "START_DATETIME": "2019-12-17T12:00:00",
        "END_DATETIME": "2020-01-22T13:00:00",
        "CORRECTION_FACTOR": 1.00776,
        "DESCRIPTION": "Counts from replacement CRS. correction factor from cross calibration",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "COCLP",
        "VARIABLE": "CTS_MOD",
        "START_DATETIME": "2017-11-16T13:00:00",
        "END_DATETIME": "2018-01-31T10:00:00",
        "CORRECTION_FACTOR": 0.99404,
        "DESCRIPTION": "Counts from replacement CRS. correction factor from cross calibration",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "HENFS",
        "VARIABLE": "CTS_MOD",
        "START_DATETIME": "2017-12-19T11:00:00",
        "END_DATETIME": "2018-06-28T13:00:00",
        "CORRECTION_FACTOR": 1.03104,
        "DESCRIPTION": "Counts from replacement CRS. correction factor from cross calibration",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "SHEEP",
        "VARIABLE": "CTS_MOD",
        "START_DATETIME": "2016-04-04T15:00:00",
        "END_DATETIME": "2016-08-24T08:30:00",
        "CORRECTION_FACTOR": 1.02015,
        "DESCRIPTION": "Counts from replacement CRS. correction factor from cross calibration",
        "METHOD_ID": "MULTIPLY",
    },
    {
        "SITE_ID": "ELMST",
        "VARIABLE": "LWIN",
        "START_DATETIME": "2021-07-14T13:00:00",
        "END_DATETIME": "2021-07-21T07:00:00",
        "CORRECTION_FACTOR": 1.00146,
        "DESCRIPTION": "Long wave radiation correction",
        "METHOD_ID": "LW_CORR",
    },
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "PRECIP",
        "START_DATETIME": "2015-03-06T00:00:00",
        "END_DATETIME": None,
        "CORRECTION_FACTOR": 0.616,
        "DESCRIPTION": "Correction for funnel size",
        "METHOD_ID": "MULTIPLY",
    },
]


def get_valid_method_ids() -> list:
    return [method["METHOD_ID"] for method in correction_methods_data]


class CorrectionMethod(BaseModel):
    METHOD_ID: str
    DESCRIPTION: str


class Correction(BaseModel):
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
        valid_methods = get_valid_method_ids()
        if v not in valid_methods:
            raise ValueError(f"Invalid METHOD_ID: {v}. Must be one of {valid_methods}")
        return v

    @field_validator("END_DATETIME")
    @classmethod
    def end_datetime_must_be_after_start(cls, v: Optional[datetime], info: ValidationInfo) -> datetime:
        if v is not None:
            start_datetime = info.data.get("START_DATETIME")
            if start_datetime and v < start_datetime:
                raise ValueError("END_DATETIME must be after START_DATETIME")
        return v

    @model_validator(mode="after")
    def check_method_variable(cls, values: "Correction") -> "Correction":
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
    correction_methods: List[CorrectionMethod]
    corrections: List[Correction]


# Instantiate the models
preprocessing_config = PreprocessingConfig(correction_methods=correction_methods_data, corrections=corrections_data)

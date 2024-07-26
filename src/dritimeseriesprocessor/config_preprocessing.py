"""
Config required for preprocessing.
This is a placeholder while a proper metadata store is being built.

The configs are built using dictionaries (update these when adding to them) and
validated with Pydantic.
Import preprocessing_config from this file to have all verified config data in
a single object.
"""

from typing import List, Literal
from pydantic import BaseModel, Field, field_validator, model_validator, ValidationError
from datetime import datetime


correction_methods_data = [
    {
        "METHOD_ID": "ADD",
        "DESCRIPTION": "Sum the data point and correction value. E.g. y=x+ C, where x is the data point and C is the change factor."
    },
    {
        "METHOD_ID": "LW_CORR",
        "DESCRIPTION": "Correction for long wave radiation where calibration values are incorrect."
    },
    {
        "METHOD_ID": "MULTIPLY",
        "DESCRIPTION": "Multiply the data point by a correction factor. E.g. y=Cx where x is the data point and C is the correction factor."
    },
    {
        "METHOD_ID": "PA_CORR",
        "DESCRIPTION": "Correction for pressure where adjust has been calculated from mean sea level pressure."
    },
    {
        "METHOD_ID": "POWER",
        "DESCRIPTION": "Raise the data point to a power. E.g. y=x^C, x is the data point and C is the change factor."
    },
    {
        "METHOD_ID": "WD_CORR",
        "DESCRIPTION": "Correction for wind direction orientation."
    },
]

corrections_data = [
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "SWOUT",
        "START_DATETIME":"2016-07-28T15:00:00",
        "END_DATETIME": "2018-12-20T12:30:00",
        "CORRECTION_FACTOR": 1.00644,
        "DESCRIPTION": "Short wave radiation correction",
        "METHOD_ID": "MULTIPLY"},
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "LWIN",
        "START_DATETIME":"2016-07-28T15:00:00",
        "END_DATETIME": "2018-12-20T12:30:00",
        "CORRECTION_FACTOR": 0.02559,
        "DESCRIPTION": "Long wave radiation correction",
        "METHOD_ID": "LW_CORR"},
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "LWOUT",
        "START_DATETIME":"2016-07-28T15:00:00",
        "END_DATETIME": "2018-12-20T12:30:00",
        "CORRECTION_FACTOR": 1.0337,
        "DESCRIPTION": "Long wave radiation correction",
        "METHOD_ID": "LW_CORR"},
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "G1",
        "START_DATETIME":"2016-07-28T14:00:00",
        "END_DATETIME": "2016-07-29T00:00:00",
        "CORRECTION_FACTOR": 0.1986,
        "DESCRIPTION": "Heat flux plate correction",
        "METHOD_ID": "MULTIPLY"},
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "G1",
        "START_DATETIME":"2016-08-01T10:30:00",
        "END_DATETIME": "2016-08-02T00:00:00",
        "CORRECTION_FACTOR": 0.1986,
        "DESCRIPTION": "Heat flux plate correction",
        "METHOD_ID": "MULTIPLY"},
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "G1",
        "START_DATETIME":"2016-08-02T10:00:00",
        "END_DATETIME": "2016-08-03T00:00:00",
        "CORRECTION_FACTOR": 0.1986,
        "DESCRIPTION": "Heat flux plate correction",
        "METHOD_ID": "MULTIPLY"},
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "G1",
        "START_DATETIME":"2016-08-17T00:30:00",
        "END_DATETIME": "2016-08-18T00:00:00",
        "CORRECTION_FACTOR": 0.1986,
        "DESCRIPTION": "Heat flux plate correction",
        "METHOD_ID": "MULTIPLY"},
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "G1",
        "START_DATETIME":"2016-08-20T06:30:00",
        "END_DATETIME": "2016-08-21T00:00:00",
        "CORRECTION_FACTOR": 0.1986,
        "DESCRIPTION": "Heat flux plate correction",
        "METHOD_ID": "MULTIPLY"},
    {
        "SITE_ID": "ALIC1",
        "VARIABLE": "G1",
        "START_DATETIME":"2016-08-21T01:30:00",
        "END_DATETIME": "2016-08-22T00:00:00",
        "CORRECTION_FACTOR": 0.1986,
        "DESCRIPTION": "Heat flux plate correction",
        "METHOD_ID": "MULTIPLY"},
]


def get_valid_method_ids():
    return [method['METHOD_ID'] for method in correction_methods_data]


class CorrectionMethod(BaseModel):
    METHOD_ID: str
    DESCRIPTION: str


class Correction(BaseModel):
    SITE_ID: str
    VARIABLE: str
    START_DATETIME: datetime
    END_DATETIME: datetime
    METHOD_ID: str = Field(..., validate_default=True)
    CORRECTION_FACTOR: float
    DESCRIPTION: str

    @field_validator('METHOD_ID')
    @classmethod
    def validate_method_id(cls, v):
        valid_methods = get_valid_method_ids()
        if v not in valid_methods:
            raise ValueError(f'Invalid METHOD_ID: {v}. Must be one of {valid_methods}')
        return v

    @model_validator(mode='after')
    def check_method_variable(cls, values):
        method_id = values.METHOD_ID
        variable = values.VARIABLE

        if method_id == 'LW_CORR' and variable not in ['LWIN', 'LWOUT']:
            raise ValueError('If METHOD_ID is "LW_CORR", VARIABLE must be either "LWIN" or "LWOUT"')
        if method_id == 'PA_CORR' and variable != 'PA':
            raise ValueError('If METHOD_ID is "PA_CORR", VARIABLE must be "PA"')
        if method_id == 'WD_CORR' and variable != 'WD':
            raise ValueError('If METHOD_ID is "WD_CORR", VARIABLE must be "WD"')

        return values


class PreprocessingConfig(BaseModel):
    correction_methods: List[CorrectionMethod]
    corrections: List[Correction]


# Instantiate the models
preprocessing_config = PreprocessingConfig(
    correction_methods=correction_methods_data,
    corrections=corrections_data
)

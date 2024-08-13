import pytest
from datetime import datetime
from pydantic import ValidationError

from dritimeseriesprocessor.__metadata__.config_preprocessing import (
    get_valid_method_ids,
    CorrectionMethod,
    Correction,
    PreprocessingConfig,
    correction_methods_data,
)

def test_get_valid_method_ids():
    """
    Test the `get_valid_method_ids` function to ensure it returns a list of
    valid method IDs.
    """
    valid_ids = get_valid_method_ids()
    assert isinstance(valid_ids, list)
    assert all(isinstance(id, str) for id in valid_ids)
    assert set(valid_ids) == set(method["METHOD_ID"] for method in correction_methods_data)

def test_correction_method():
    """
    Test the `CorrectionMethod` model to ensure it can be instantiated
    correctly and raises errors for missing input.
    """
    method = CorrectionMethod(METHOD_ID="TEST", DESCRIPTION="Test method")
    assert method.METHOD_ID == "TEST"
    assert method.DESCRIPTION == "Test method"

    with pytest.raises(ValidationError):
        CorrectionMethod(DESCRIPTION="Test method")

def test_correction_valid():
    """
    Test the `Correction` model to ensure it can be instantiated with valid
    data.
    """
    correction = Correction(
        SITE_ID="TEST",
        VARIABLE="TEMP",
        START_DATETIME=datetime(2023, 1, 1),
        END_DATETIME=datetime(2023, 1, 2),
        METHOD_ID="ADD",
        CORRECTION_FACTOR=1.0,
        DESCRIPTION="Test correction"
    )
    assert correction.SITE_ID == "TEST"
    assert correction.VARIABLE == "TEMP"
    assert correction.START_DATETIME == datetime(2023, 1, 1)
    assert correction.END_DATETIME == datetime(2023, 1, 2)
    assert correction.METHOD_ID == "ADD"
    assert correction.CORRECTION_FACTOR == 1.0
    assert correction.DESCRIPTION == "Test correction"

def test_correction_invalid_method_id():
    """
    Test the `Correction` model to ensure it raises a validation error for an
    invalid METHOD_ID.
    """
    with pytest.raises(ValidationError):
        Correction(
            SITE_ID="TEST",
            VARIABLE="TEMP",
            START_DATETIME=datetime(2023, 1, 1),
            METHOD_ID="INVALID",
            CORRECTION_FACTOR=1.0,
            DESCRIPTION="Test correction"
        )

def test_correction_end_datetime_before_start():
    """
    Test the `Correction` model to ensure it raises a validation error if
    END_DATETIME is before START_DATETIME.
    """
    with pytest.raises(ValidationError):
        Correction(
            SITE_ID="TEST",
            VARIABLE="TEMP",
            START_DATETIME=datetime(2023, 1, 2),
            END_DATETIME=datetime(2023, 1, 1),
            METHOD_ID="ADD",
            CORRECTION_FACTOR=1.0,
            DESCRIPTION="Test correction"
        )

def test_correction_lw_corr_valid():
    """
    Test the `Correction` model to ensure it can be instantiated with a valid
    LW_CORR METHOD_ID.
    """
    correction = Correction(
        SITE_ID="TEST",
        VARIABLE="LWIN",
        START_DATETIME=datetime(2023, 1, 1),
        METHOD_ID="LW_CORR",
        CORRECTION_FACTOR=1.0,
        DESCRIPTION="Test correction"
    )
    assert correction.METHOD_ID == "LW_CORR"
    assert correction.VARIABLE == "LWIN"

def test_correction_lw_corr_invalid():
    """
    Test the `Correction` model to ensure it raises a validation error for an
    invalid VARIABLE with LW_CORR METHOD_ID.
    """
    with pytest.raises(ValidationError):
        Correction(
            SITE_ID="TEST",
            VARIABLE="TEMP",
            START_DATETIME=datetime(2023, 1, 1),
            METHOD_ID="LW_CORR",
            CORRECTION_FACTOR=1.0,
            DESCRIPTION="Test correction"
        )

def test_correction_pa_corr_valid():
    """
    Test the `Correction` model to ensure it can be instantiated with a valid
    PA_CORR METHOD_ID.
    """
    correction = Correction(
        SITE_ID="TEST",
        VARIABLE="PA",
        START_DATETIME=datetime(2023, 1, 1),
        METHOD_ID="PA_CORR",
        CORRECTION_FACTOR=1.0,
        DESCRIPTION="Test correction"
    )
    assert correction.METHOD_ID == "PA_CORR"
    assert correction.VARIABLE == "PA"

def test_correction_pa_corr_invalid():
    """
    Test the `Correction` model to ensure it raises a validation error for an
    invalid VARIABLE with PA_CORR METHOD_ID.
    """
    with pytest.raises(ValidationError):
        Correction(
            SITE_ID="TEST",
            VARIABLE="TEMP",
            START_DATETIME=datetime(2023, 1, 1),
            METHOD_ID="PA_CORR",
            CORRECTION_FACTOR=1.0,
            DESCRIPTION="Test correction"
        )

def test_preprocessing_config():
    """
    Test the `PreprocessingConfig` model to ensure it can be instantiated with
    valid correction methods and corrections.
    """
    config = PreprocessingConfig(
        correction_methods=[
            CorrectionMethod(METHOD_ID="ADD", DESCRIPTION="Add method"),
            CorrectionMethod(METHOD_ID="MULTIPLY", DESCRIPTION="Multiply method")
        ],
        corrections=[
            Correction(
                SITE_ID="TEST1",
                VARIABLE="TEMP",
                START_DATETIME=datetime(2023, 1, 1),
                METHOD_ID="ADD",
                CORRECTION_FACTOR=1.0,
                DESCRIPTION="Test correction 1"
            ),
            Correction(
                SITE_ID="TEST2",
                VARIABLE="LWIN",
                START_DATETIME=datetime(2023, 1, 1),
                METHOD_ID="LW_CORR",
                CORRECTION_FACTOR=1.0,
                DESCRIPTION="Test correction 2"
            )
        ]
    )
    assert len(config.correction_methods) == 2
    assert len(config.corrections) == 2

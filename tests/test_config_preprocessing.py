import pytest
from datetime import datetime, timedelta
from pydantic import ValidationError

# Assuming the classes and functions are in a module named 'your_module'
from dritimeseriesprocessor.config_preprocessing import (
    get_valid_method_ids,
    CorrectionMethod,
    Correction,
    PreprocessingConfig,
    correction_methods_data,
)

def test_get_valid_method_ids():
    valid_ids = get_valid_method_ids()
    assert isinstance(valid_ids, list)
    assert all(isinstance(id, str) for id in valid_ids)
    assert set(valid_ids) == set(method["METHOD_ID"] for method in correction_methods_data)

def test_correction_method():
    method = CorrectionMethod(METHOD_ID="TEST", DESCRIPTION="Test method")
    assert method.METHOD_ID == "TEST"
    assert method.DESCRIPTION == "Test method"

    with pytest.raises(ValidationError):
        CorrectionMethod(DESCRIPTION="Test method")

def test_correction_valid():
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

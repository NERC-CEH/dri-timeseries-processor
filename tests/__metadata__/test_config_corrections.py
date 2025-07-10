import pytest
from datetime import datetime
from pydantic import ValidationError

from dritimeseriesprocessor.__metadata__.config_corrections import (
    get_valid_method_ids,
    CorrectionMethod,
    Correction,
    CorrectionsConfig,
    correction_methods_data,
)

def test_get_valid_method_ids():
    """
    Test the `get_valid_method_ids` function to ensure it returns a list of
    valid method IDs.
    """
    valid_ids = get_valid_method_ids()
    assert isinstance(valid_ids, list)
    assert all(isinstance(meth_id, str) for meth_id in valid_ids)
    assert set(valid_ids) == set(method["method_id"] for method in correction_methods_data)

def test_correction_method():
    """
    Test the `CorrectionMethod` model to ensure it can be instantiated
    correctly and raises errors for missing input.
    """
    method = CorrectionMethod(method_id="TEST", description="Test method", id=1)
    assert method.method_id == "TEST"
    assert method.description == "Test method"

    with pytest.raises(ValidationError):
        CorrectionMethod(description="Test method")

def test_correction_valid():
    """
    Test the `Correction` model to ensure it can be instantiated with valid
    data.
    """
    correction = Correction(
        site_id="TEST",
        variable="TEMP",
        start_datetime=datetime(2023, 1, 1),
        end_datetime=datetime(2023, 1, 2),
        method_id="ADD",
        correction_factor=1.0,
        description="Test correction"
    )
    assert correction.site_id == "TEST"
    assert correction.variable == "TEMP"
    assert correction.start_datetime == datetime(2023, 1, 1)
    assert correction.end_datetime == datetime(2023, 1, 2)
    assert correction.method_id == "ADD"
    assert correction.correction_factor == 1.0
    assert correction.description == "Test correction"

def test_correction_invalid_method_id():
    """
    Test the `Correction` model to ensure it raises a validation error for an
    invalid method_id.
    """
    with pytest.raises(ValidationError):
        Correction(
            site_id="TEST",
            variable="TEMP",
            start_datetime=datetime(2023, 1, 1),
            method_id="INVALID",
            correction_factor=1.0,
            description="Test correction"
        )

def test_correction_end_datetime_before_start():
    """
    Test the `Correction` model to ensure it raises a validation error if
    end_datetime is before start_datetime.
    """
    with pytest.raises(ValidationError):
        Correction(
            site_id="TEST",
            variable="TEMP",
            start_datetime=datetime(2023, 1, 2),
            end_datetime=datetime(2023, 1, 1),
            method_id="ADD",
            correction_factor=1.0,
            description="Test correction"
        )

def test_correction_lw_corr_valid():
    """
    Test the `Correction` model to ensure it can be instantiated with a valid
    LW_CORR method_id.
    """
    correction = Correction(
        site_id="TEST",
        variable="LWIN",
        start_datetime=datetime(2023, 1, 1),
        method_id="LW_CORR",
        correction_factor=1.0,
        description="Test correction"
    )
    assert correction.method_id == "LW_CORR"
    assert correction.variable == "LWIN"

def test_correction_lw_corr_invalid():
    """
    Test the `Correction` model to ensure it raises a validation error for an
    invalid variable with LW_CORR method_id.
    """
    with pytest.raises(ValidationError):
        Correction(
            site_id="TEST",
            variable="TEMP",
            start_datetime=datetime(2023, 1, 1),
            method_id="LW_CORR",
            correction_factor=1.0,
            description="Test correction"
        )

def test_correction_pa_corr_valid():
    """
    Test the `Correction` model to ensure it can be instantiated with a valid
    PA_CORR method_id.
    """
    correction = Correction(
        site_id="TEST",
        variable="PA",
        start_datetime=datetime(2023, 1, 1),
        method_id="PA_CORR",
        correction_factor=1.0,
        description="Test correction"
    )
    assert correction.method_id == "PA_CORR"
    assert correction.variable == "PA"

def test_correction_pa_corr_invalid():
    """
    Test the `Correction` model to ensure it raises a validation error for an
    invalid variable with PA_CORR method_id.
    """
    with pytest.raises(ValidationError):
        Correction(
            site_id="TEST",
            variable="TEMP",
            start_datetime=datetime(2023, 1, 1),
            method_id="PA_CORR",
            correction_factor=1.0,
            description="Test correction"
        )

def test_corrections_config():
    """
    Test the `CorrectionsConfig` model to ensure it can be instantiated with
    valid correction methods and corrections.
    """
    config = CorrectionsConfig(
        correction_methods=[
            CorrectionMethod(method_id="ADD", description="Add method", id=1),
            CorrectionMethod(method_id="MULTIPLY", description="Multiply method", id=2)
        ],
        corrections=[
            Correction(
                site_id="TEST1",
                variable="TEMP",
                start_datetime=datetime(2023, 1, 1),
                method_id="ADD",
                correction_factor=1.0,
                description="Test correction 1"
            ),
            Correction(
                site_id="TEST2",
                variable="LWIN",
                start_datetime=datetime(2023, 1, 1),
                method_id="LW_CORR",
                correction_factor=1.0,
                description="Test correction 2"
            )
        ]
    )
    assert len(config.correction_methods) == 2
    assert len(config.corrections) == 2

import pytest
from pydantic import ValidationError
from dritimeseriesprocessor.config_quality_control import (
    get_valid_qc_tests,
    QCTest,
    RangeThreshold,
    VariableRangeThreshold,
    VariableTestMapping,
    QCConfig,
    qc_tests,
    default_range_thresholds,
    variable_test_mapping
)
from dritimeseriesprocessor.utils import validate_iso8601_duration


def test_get_valid_qc_tests():
    """
    Test that get_valid_qc_tests returns the correct list of QC test names.
    """
    expected_tests = [qc_test["test_name"] for qc_test in qc_tests]
    assert get_valid_qc_tests() == expected_tests


def test_qc_test_model():
    """
    Test the QCTest model to ensure it initializes with the correct test_name and description.
    """
    qc_test = QCTest(test_name="RANGE", description="Checks if the value falls within a specified range.")
    assert qc_test.test_name == "RANGE"
    assert qc_test.description == "Checks if the value falls within a specified range."


def test_range_threshold_valid():
    """
    Test the RangeThreshold model with valid min_value and max_value.
    """
    range_threshold = RangeThreshold(min_value=-10.0, max_value=10.0)
    assert range_threshold.min_value == -10.0
    assert range_threshold.max_value == 10.0


def test_range_threshold_equal_min_max():
    """
    Test that no error is raised if min_value is equal to max_value in RangeThreshold.
    """
    range_threshold = RangeThreshold(min_value=10.0, max_value=10.0)
    assert range_threshold.min_value == 10.0
    assert range_threshold.max_value == 10.0


def test_range_threshold_invalid_max_less_than_min():
    """
    Test that a ValueError is raised if max_value is less than min_value in RangeThreshold.
    """
    with pytest.raises(ValueError, match='max_value must be greater than min_value'):
        RangeThreshold(min_value=10.0, max_value=-10.0)


def test_variable_range_threshold_valid_default():
    """
    Test the VariableRangeThreshold model with a default RangeThreshold.
    """
    variable_range_threshold = VariableRangeThreshold(
        variable_name="TA",
        default=RangeThreshold(min_value=-10.0, max_value=10.0)
    )
    assert variable_range_threshold.variable_name == "TA"
    assert variable_range_threshold.default.min_value == -10.0
    assert variable_range_threshold.default.max_value == 10.0
    assert variable_range_threshold.resolutions is None


def test_variable_range_threshold_valid_resolutions():
    """
    Test the VariableRangeThreshold model with valid resolution-specific thresholds.
    """
    variable_range_threshold = VariableRangeThreshold(
        variable_name="PRECIP",
        resolutions={
            "PT1M": RangeThreshold(min_value=0.0, max_value=10.0),
            "PT30M": RangeThreshold(min_value=0.0, max_value=100.0)
        }
    )
    assert variable_range_threshold.variable_name == "PRECIP"
    assert len(variable_range_threshold.resolutions) == 2


def test_variable_range_threshold_invalid_duration():
    """
    Test that a ValueError is raised if an invalid ISO 8601 duration is used in the resolutions.
    """
    with pytest.raises(ValueError, match="Invalid ISO 8601 duration: invalid"):
        VariableRangeThreshold(
            variable_name="PRECIP",
            resolutions={
                "invalid": RangeThreshold(min_value=0.0, max_value=10.0)
            }
        )


def test_variable_range_threshold_mutually_exclusive():
    """
    Test that a ValueError is raised if both default and resolutions are provided in VariableRangeThreshold.
    """
    with pytest.raises(ValueError, match="Only one of 'default' or 'resolutions' can be provided, not both"):
        VariableRangeThreshold(
            variable_name="PRECIP",
            default=RangeThreshold(min_value=-10.0, max_value=10.0),
            resolutions={
                "PT1M": RangeThreshold(min_value=0.0, max_value=10.0)
            }
        )


def test_variable_range_threshold_neither_provided():
    """
    Test that a ValueError is raised if neither default nor resolutions is provided in VariableRangeThreshold.
    """
    with pytest.raises(ValueError, match="Either 'default' or 'resolutions' must be provided"):
        VariableRangeThreshold(variable_name="PRECIP")


def test_variable_test_mapping_valid():
    """
    Test the VariableTestMapping model with valid variable_name and tests.
    """
    variable_test_mapping = VariableTestMapping(
        variable_name="TA",
        tests=["RANGE"]
    )
    assert variable_test_mapping.variable_name == "TA"
    assert variable_test_mapping.tests == ["RANGE"]


def test_variable_test_mapping_invalid_test():
    """
    Test that a ValueError is raised if an invalid QC test is specified in
    VariableTestMapping.
    """
    with pytest.raises(ValueError, match="Test 'INVALID' is not a valid QC test"):
        VariableTestMapping(
            variable_name="TA",
            tests=["INVALID"]
        )


def test_qc_config_valid():
    """
    Test the QCConfig model with valid configuration data.
    """
    qc_config = QCConfig(
        qc_tests=[QCTest(**qc_test) for qc_test in qc_tests],
        default_range_thresholds=[VariableRangeThreshold(**range_thresh)
                                  for range_thresh in default_range_thresholds],
        variable_test_mapping=[VariableTestMapping(**var_test_map)
                               for var_test_map in variable_test_mapping]
    )
    assert len(qc_config.qc_tests) == len(qc_tests)
    assert len(qc_config.default_range_thresholds) == len(default_range_thresholds)
    assert len(qc_config.variable_test_mapping) == len(variable_test_mapping)


def test_qc_config_invalid():
    """
    Test that a ValidationError is raised if the QCConfig is instantiated with
    invalid mappings.
    """
    with pytest.raises(ValidationError):
        QCConfig(
            qc_tests=[QCTest(**qc_test) for qc_test in qc_tests],
            default_range_thresholds=[VariableRangeThreshold(**range_thresh)
                                      for range_thresh in default_range_thresholds],
            variable_test_mapping="Invalid type"
        )

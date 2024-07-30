import unittest
from pydantic import ValidationError

from dritimeseriesprocessor.config_quality_control import (
    qc_tests,
    QCTest,
    RangeThreshold,
    VariableRangeThresholds,
    VariableTestMapping,
    QCConfig,
    get_valid_qc_tests
)

class TestGetValidQCTests(unittest.TestCase):
    def test_get_valid_qc_tests(self):
        """Test that get_valid_qc_tests returns the correct list of QC test names.
        """
        expected_tests = [qc_test["test_name"] for qc_test in qc_tests]
        assert get_valid_qc_tests() == expected_tests


class TestQCTest(unittest.TestCase):
    def test_valid_qc_test(self):
        """Test that a valid QCTest instance is created correctly."""
        qc_test = QCTest(test_name="RANGE", description="Checks if the value falls within a specified range.")
        self.assertEqual(qc_test.test_name, "RANGE")
        self.assertEqual(qc_test.description, "Checks if the value falls within a specified range.")


class TestRangeThreshold(unittest.TestCase):
    def test_valid_range_threshold(self):
        """Test that a valid RangeThreshold instance is created correctly."""
        range_threshold = RangeThreshold(min_value=0.0, max_value=10.0)
        self.assertEqual(range_threshold.min_value, 0.0)
        self.assertEqual(range_threshold.max_value, 10.0)

    def test_range_threshold_equal_min_max(self):
        """Test that no error is raised if min_value is equal to max_value.
        """
        range_threshold = RangeThreshold(min_value=10.0, max_value=10.0)
        self.assertEqual(range_threshold.min_value, 10.0)
        self.assertEqual(range_threshold.max_value, 10.0)

    def test_max_value_less_than_min_value(self):
        """Test that an error is raised if max_value is less than min_value."""
        with self.assertRaises(ValidationError):
            RangeThreshold(min_value=10.0, max_value=0.0)

    def test_invalid_resolution(self):
        """Test that an error is raised for an invalid ISO 8601 duration in resolutions."""
        with self.assertRaises(ValidationError):
            RangeThreshold(min_value=0.0, max_value=10.0, resolutions=["INVALID"])


class TestVariableRangeThresholds(unittest.TestCase):
    def test_valid_variable_range_thresholds(self):
        """Test that a valid VariableRangeThresholds instance is created correctly."""
        defaults = [RangeThreshold(min_value=0.0, max_value=10.0)]
        sites = [RangeThreshold(site_id="SITE1", min_value=0.0, max_value=10.0)]
        variable_range_thresholds = VariableRangeThresholds(variable_id="TA", defaults=defaults, sites=sites)
        self.assertEqual(variable_range_thresholds.variable_id, "TA")
        self.assertEqual(variable_range_thresholds.defaults, defaults)
        self.assertEqual(variable_range_thresholds.sites, sites)

    def test_missing_site_id_in_sites(self):
        """Test that an error is raised if a RangeThreshold in 'sites' does not contain a 'site_id'."""
        defaults = [RangeThreshold(min_value=0.0, max_value=10.0)]
        sites = [RangeThreshold(min_value=0.0, max_value=10.0)]
        with self.assertRaises(ValidationError):
            VariableRangeThresholds(variable_id="TA", defaults=defaults, sites=sites)


class TestVariableTestMapping(unittest.TestCase):
    def test_valid_variable_test_mapping(self):
        """Test that a valid VariableTestMapping instance is created correctly."""
        variable_test_mapping = VariableTestMapping(variable_id="TA", tests=["RANGE"])
        self.assertEqual(variable_test_mapping.variable_id, "TA")
        self.assertEqual(variable_test_mapping.tests, ["RANGE"])

    def test_invalid_test_name(self):
        """Test that an error is raised for an invalid test name."""
        with self.assertRaises(ValidationError):
            VariableTestMapping(variable_id="TA", tests=["INVALID_TEST"])


class TestQCConfig(unittest.TestCase):
    def test_valid_qc_config(self):
        """Test that a valid QCConfig instance is created correctly."""
        qc_tests = [QCTest(test_name="RANGE", description="Checks if the value falls within a specified range.")]
        var_range_thresholds = [
            VariableRangeThresholds(
                variable_id="TA",
                defaults=[RangeThreshold(min_value=-30.0, max_value=55.0)],
                sites=[RangeThreshold(site_id="BUNNY", resolutions=["PT1M"], min_value=-25.0, max_value=50.0)]
            )
        ]
        variable_test_mapping = [VariableTestMapping(variable_id="TA", tests=["RANGE"])]
        qc_config = QCConfig(qc_tests=qc_tests, var_range_thresholds=var_range_thresholds, variable_test_mapping=variable_test_mapping)
        self.assertEqual(qc_config.qc_tests, qc_tests)
        self.assertEqual(qc_config.var_range_thresholds, var_range_thresholds)
        self.assertEqual(qc_config.variable_test_mapping, variable_test_mapping)

    def test_qc_config_invalid(self):
        """Test that a ValidationError is raised if the QCConfig is instantiated with
        invalid mappings.
        """
        qc_tests = [QCTest(test_name="RANGE", description="Checks if the value falls within a specified range.")]
        var_range_thresholds = [
            VariableRangeThresholds(
                variable_id="TA",
                defaults=[RangeThreshold(min_value=-30.0, max_value=55.0)],
                sites=[RangeThreshold(site_id="BUNNY", resolutions=["PT1M"], min_value=-25.0, max_value=50.0)]
            )
        ]
        with self.assertRaises(ValidationError):
            QCConfig(
                qc_tests=qc_tests,
                var_range_thresholds=var_range_thresholds,
                variable_test_mapping="invalid")


if __name__ == '__main__':
    unittest.main()

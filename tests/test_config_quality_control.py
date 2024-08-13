import unittest
from unittest.mock import patch
from pydantic import ValidationError

from dritimeseriesprocessor.config_quality_control import (
    qc_tests,
    var_range_thresholds,
    variable_test_mapping,
    QCTest,
    RangeThreshold,
    VariableRangeThresholds,
    ValueTreshold,
    VariableTestMapping,
    QCConfig,
    get_valid_qc_tests,
    get_qc_config,
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
        qc_config = QCConfig(qc_tests=qc_tests, var_range_thresholds=var_range_thresholds,
                             variable_test_mapping=variable_test_mapping, battv_threshold=ValueTreshold(threshold=10))
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


class TestGetQCConfig(unittest.TestCase):

    def setUp(self):
        """Set up the test environment by mocking the global variables used in get_qc_config.
        This method is called before each test method.
        """
        mock_qc_test = [
            {
                "test_name": "RANGE",
                "description": "Checks if the value falls within a specified range.",
            },
        ]

        qc_test_patch = patch('dritimeseriesprocessor.config_quality_control.qc_tests',
                              mock_qc_test)
        qc_test_patch.start()
        
        mock_var_range_threshs = [
            {
                "variable_id": "TA",
                "defaults": [
                    {
                        "min_value": -30.0,
                        "max_value": 55.0,
                    },
                ],
                "sites": [
                    {
                        "site_id": "BUNNY",
                        "resolutions": ["PT1M", "PT15M", "PT30M"],
                        "min_value": -25.0,
                        "max_value": 50.0,
                    },
                ],
            },
        ]
        var_range_patch = patch('dritimeseriesprocessor.config_quality_control.var_range_thresholds',
                                mock_var_range_threshs)
        var_range_patch.start()

        mock_var_test_map = [
            {
                "variable_id": "TA",
                "tests": [
                    "RANGE",
                ],
            },
        ]
        variable_test_map_patch = patch('dritimeseriesprocessor.config_quality_control.variable_test_mapping',
                                        mock_var_test_map)
        variable_test_map_patch.start()


    def test_get_all_config(self):
        """Test the get_qc_config function with 'all' configuration.
        Verifies that it returns a QCConfig object with the correct number of items
        in each attribute.
        """
        result = get_qc_config("all")
        self.assertEqual(len(result.qc_tests), 1)
        self.assertEqual(len(result.var_range_thresholds), 1)
        self.assertEqual(len(result.variable_test_mapping), 1)
        self.assertIsInstance(result, QCConfig)

    def test_get_tests_config(self):
        """Test the get_qc_config function with 'tests' configuration.
        Verifies that it returns a list of QCTest objects with the correct content.
        """
        result = get_qc_config("tests")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], QCTest)
        self.assertEqual(result[0].test_name, "RANGE")

    def test_get_range_thresholds_config(self):
        """Test the get_qc_config function with 'range_thresholds' configuration.
        Verifies that it returns a list of VariableRangeThresholds objects
        with the correct content.
        """
        result = get_qc_config("range_thresholds")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], VariableRangeThresholds)
        self.assertEqual(result[0].variable_id, "TA")

    def test_get_variable_test_map_config(self):
        """Test the get_qc_config function with 'variable_test_map' configuration.
        Verifies that it returns a list of VariableTestMapping objects
        with the correct content.
        """
        result = get_qc_config("variable_test_map")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], VariableTestMapping)
        self.assertEqual(result[0].variable_id, "TA")

    def test_invalid_config_type(self):
        """Test the get_qc_config function with an invalid configuration type.
        Verifies that it raises a ValueError.
        """
        with self.assertRaises(ValueError):
            get_qc_config("invalid_type")

    def test_default_config(self):
        """Test the get_qc_config function with default configuration (no argument).
        Verifies that it returns a QCConfig object, which is equivalent to 'all' configuration.
        """
        result = get_qc_config()
        self.assertIsInstance(result, QCConfig)


if __name__ == '__main__':
    unittest.main()

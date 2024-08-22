import unittest
from unittest.mock import patch
from pydantic import ValidationError

from dritimeseriesprocessor.__metadata__.config_quality_control import (
    QCTest,
    RangeThreshold,
    VariableRangeThresholds,
    get_qc_config,
)


class TestQCTest(unittest.TestCase):
    def test_valid_qc_test(self):
        """Test that a valid QCTest instance is created correctly."""
        qc_test = QCTest(test_name="Range test", description="Checks if the value falls within a specified range.",
                         variables=["TA", "PRECIP"], id=1)
        self.assertEqual(qc_test.test_name, "Range test")
        self.assertEqual(qc_test.description, "Checks if the value falls within a specified range.")
        self.assertEqual(qc_test.variables, ["TA", "PRECIP"])
        self.assertEqual(qc_test.id, 1)


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
        variable_range_thresholds = VariableRangeThresholds(defaults=defaults, sites=sites)
        self.assertEqual(variable_range_thresholds.defaults, defaults)
        self.assertEqual(variable_range_thresholds.sites, sites)

    def test_missing_site_id_in_sites(self):
        """Test that an error is raised if a RangeThreshold in 'sites' does not contain a 'site_id'."""
        defaults = [RangeThreshold(min_value=0.0, max_value=10.0)]
        sites = [RangeThreshold(min_value=0.0, max_value=10.0)]
        with self.assertRaises(ValidationError):
            VariableRangeThresholds(variable="TA", defaults=defaults, sites=sites)


class TestGetQCConfig(unittest.TestCase):

    def setUp(self):
        """Set up the test environment by mocking the global variables used in get_qc_config.
        This method is called before each test method.
        """
        mock_qc_test = {
            "RANGE": {
                "test_name": "Range test",
                "id": 1 << 0,
                "description": "Checks if the value falls within a specified range.",
                "variables": ["TA", "PRECIP"]
            },
        }

        qc_test_patch = patch('dritimeseriesprocessor.__metadata__.config_quality_control.qc_tests',
                              mock_qc_test)

        mock_var_range_threshs = {
            "TA": {
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
        }
        var_range_patch = patch('dritimeseriesprocessor.__metadata__.config_quality_control.var_range_thresholds',
                                mock_var_range_threshs)

        self.patches = [var_range_patch, qc_test_patch]

        [p.start() for p in self.patches]

    def tearDown(self):
        [p.stop() for p in self.patches]

    def test_get_tests_config(self):
        """Test the get_qc_config function with 'qc_tests' configuration.
        Verifies that it returns a dictionary of QCTest objects with the correct content.
        """
        result = get_qc_config("qc_tests")
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result["RANGE"], QCTest)
        self.assertEqual(result["RANGE"].test_name, "Range test")

    def test_get_range_thresholds_config(self):
        """Test the get_qc_config function with 'range_thresholds' configuration.
        Verifies that it returns a list of VariableRangeThresholds objects
        with the correct content.
        """
        result = get_qc_config("range_thresholds")
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result["TA"], VariableRangeThresholds)

    def test_invalid_config_type(self):
        """Test the get_qc_config function with an invalid configuration type.
        Verifies that it raises a ValueError.
        """
        with self.assertRaises(ValueError):
            get_qc_config("invalid_type")

import unittest
from unittest.mock import patch
from typing import Dict, List, Any
from pydantic import ValidationError
from dritimeseriesprocessor.__metadata__.config_infilling import (
    InfillMethod,
    Method,
    VariableResolutionMethods,
    get_infill_config
)


# Mock data for testing
mock_infill_methods: Dict[str, Dict[str, Any]] = {
    "INTERP_LINEAR": {"name": "Method 1", "description": "Description 1", "requirements": {}, "id": 1},
    "INTERP_POLY2": {"name": "Method 2", "description": "Description 2", "requirements": {}, "id": 2},
}

mock_variables: Dict[str, Dict[str, Any]] = {
    "var1": {
        "res1": {
            "methods": [
                {"method": "INTERP_LINEAR", "priority": 1, "constraints": {}},
                {"method": "INTERP_POLY2", "priority": 2, "constraints": {}},
            ]
        }
    }
}

class TestInfillMethod(unittest.TestCase):
    def test_infill_method(self) -> None:
        """Test the InfillMethod class creation."""
        method = InfillMethod(name="Test Method", description="Test Description", requirements={}, id=1)
        self.assertEqual(method.name, "Test Method")
        self.assertEqual(method.description, "Test Description")
        self.assertEqual(method.requirements, {})
        self.assertEqual(method.id, 1)

    def test_infill_method_missing_attributes(self) -> None:
        """Test InfillMethod creation with missing attributes."""
        with self.assertRaises(ValidationError):
            InfillMethod(name="Test Method")  # Missing description and requirements


class TestMethod(unittest.TestCase):
    @patch('dritimeseriesprocessor.__metadata__.config_infilling.infill_methods', mock_infill_methods)
    def test_method_valid(self) -> None:
        """Test the Method class with valid input."""
        method = Method(method="INTERP_LINEAR", priority=1, constraints={})
        self.assertEqual(method.method, "INTERP_LINEAR")
        self.assertEqual(method.priority, 1)
        self.assertEqual(method.constraints, {})

    @patch('dritimeseriesprocessor.__metadata__.config_infilling.infill_methods', mock_infill_methods)
    def test_method_invalid_id(self) -> None:
        """Test Method class with invalid method."""
        with self.assertRaises(ValidationError):
            Method(method="invalid_method", priority=1, constraints={})


class TestVariableResolutionMethods(unittest.TestCase):
    @patch('dritimeseriesprocessor.__metadata__.config_infilling.infill_methods', mock_infill_methods)
    def test_variable_resolution_methods_valid(self) -> None:
        """Test the VariableResolutionMethods class with valid methods."""
        methods: List[Dict[str, Any]] = [
            {"method": "INTERP_LINEAR", "priority": 1, "constraints": {}},
            {"method": "INTERP_POLY2", "priority": 2, "constraints": {}},
        ]
        vrm = VariableResolutionMethods(methods=methods)
        self.assertEqual(len(vrm.methods), 2)

    def test_variable_resolution_methods_duplicate_priority(self) -> None:
        """Test VariableResolutionMethods with duplicate priorities."""
        methods: List[Dict[str, Any]] = [
            {"method": "INTERP_LINEAR", "priority": 1, "constraints": {}},
            {"method": "INTERP_POLY2", "priority": 1, "constraints": {}},
        ]
        with self.assertRaises(ValueError, msg="All method priorities must be unique"):
            VariableResolutionMethods(methods=methods)


class TestGetInfillConfig(unittest.TestCase):
    @patch('dritimeseriesprocessor.__metadata__.config_infilling.infill_methods', mock_infill_methods)
    @patch('dritimeseriesprocessor.__metadata__.config_infilling.variables', mock_variables)
    def test_get_infill_config_infill_methods(self) -> None:
        """Test get_infill_config for infill_methods."""
        config = get_infill_config("infill_methods")
        self.assertIsInstance(config, dict)
        self.assertIn("INTERP_LINEAR", config)
        self.assertIsInstance(config["INTERP_LINEAR"], InfillMethod)

    @patch('dritimeseriesprocessor.__metadata__.config_infilling.infill_methods', mock_infill_methods)
    @patch('dritimeseriesprocessor.__metadata__.config_infilling.variables', mock_variables)
    def test_get_infill_config_variables(self) -> None:
        """Test get_infill_config for variables."""
        config = get_infill_config("variables")
        self.assertIsInstance(config, dict)
        self.assertIn("var1", config)
        self.assertIn("res1", config["var1"])
        self.assertIsInstance(config["var1"]["res1"], VariableResolutionMethods)

    def test_get_infill_config_invalid(self) -> None:
        """Test get_infill_config with invalid config type."""
        with self.assertRaises(ValueError, msg="Not a valid config type"):
            get_infill_config("invalid_type")

if __name__ == '__main__':
    unittest.main()
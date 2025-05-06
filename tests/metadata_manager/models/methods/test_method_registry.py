import unittest
from parameterized import parameterized
from unittest.mock import patch, MagicMock

from metadata_manager.models.methods.method_registry import (
    Method,
    MethodType,
    InfillingMethods,
    QcMethods
)


class TestMethod(unittest.TestCase):
    def setUp(self):
        self.method_dict = {
            "method_type": "infilling",
            "name": "method name",
            "description": "description",
            "id": 1,
            "function_name": "a_function_name"
        }

    def test_valid_method(self):
        """Test that valid arguments create a valid method."""
        method = Method.model_validate(self.method_dict)

        self.assertEqual(method.method_id, 1)
        self.assertEqual(method.method_type, MethodType.INFILLING)
        self.assertEqual(method.name, "method name")
        self.assertEqual(method.description, "description")
        self.assertEqual(method.function_name, "a_function_name")

    @parameterized.expand([
        ("test_zero", 0),
        ("test_negative", -1),
    ])
    def test_invalid_method_id(self, _, method_id):
        """Test that invalid method_id values are rejected."""
        method_dict = self.method_dict.copy()
        method_dict["id"] = method_id
        with self.assertRaises(ValueError):
            Method.model_validate(method_dict)

    def test_invalid_name(self):
        """Test that empty names are rejected."""
        method_dict = self.method_dict.copy()
        method_dict["name"] = ""
        with self.assertRaises(ValueError):
            Method.model_validate(method_dict)

    def test_call_method(self):
        """Test calling the method invokes the correct function with correct arguments."""
        method_dict = self.method_dict.copy()
        method_dict["function_name"] = "linear_interpolation"
        
        mock_function = MagicMock(return_value="test_result")
        with patch('dritimeseriesprocessor.infilling.methods.linear_interpolation', mock_function):
            method = Method.model_validate(method_dict)
            result = method(arg1="value1", arg2="value2")
            mock_function.assert_called_once_with(arg1="value1", arg2="value2")
            self.assertEqual(result, "test_result")

    def test_call_missing_function(self):
        """Test that calling a non-existent function raises ValueError."""
        method = Method.model_validate(self.method_dict)
        with self.assertRaises(ValueError):
            method()


class TestMethodRegisters(unittest.TestCase):
    @parameterized.expand([
        (InfillingMethods, MethodType.INFILLING),
        (QcMethods, MethodType.QC),
    ])
    def test_model_validate(self, registry_class, method_type):
        """Test that model_validate correctly transforms and registers methods."""
        test_data = {
            "method1": {
                "id": 1,
                "name": "Method 1",
                "description": "Description of method 1",
                "function_name": "method_1"
            },
            "method2": {
                "id": 2,
                "name": "Method 2",
                "description": "Description of method 2",
                "function_name": "method_2"
            },
        }
        registry = registry_class.model_validate(test_data)
        self.assertEqual(set(registry.keys()), {"method1", "method2"})
        self.assertEqual(registry["method1"].method_type, method_type)
        self.assertEqual(registry["method2"].method_type, method_type)

    @parameterized.expand([
        InfillingMethods,
        QcMethods,
    ])
    @patch("metadata_manager.models.methods.method_registry.Method.model_validate")
    def test_validate_called_for_each_method(self, registry_class, mock_validate):
        """Test that InfillingMethod.model_validate is called for each method."""
        mock_method = MagicMock(spec=Method)
        mock_validate.return_value = mock_method

        test_data = {
            "method1": {"id": 1, "name": "Method 1", "description": "Description 1", "function_name": "func1"},
            "method2": {"id": 2, "name": "Method 2", "description": "Description 2", "function_name": "func2"},
            "method3": {"id": 3, "name": "Method 3", "description": "Description 3", "function_name": "func3"}
        }

        registry_class.model_validate(test_data)
        self.assertEqual(mock_validate.call_count, 3)

    @parameterized.expand([
        InfillingMethods,
        QcMethods,
    ])
    def test_empty_data(self, registry_class):
        """Test that empty data results in an empty registry."""
        test_data = {}
        registry = registry_class.model_validate(test_data)
        self.assertEqual(len(registry), 0)

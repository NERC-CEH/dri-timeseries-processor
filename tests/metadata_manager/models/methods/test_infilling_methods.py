import unittest
from parameterized import parameterized
from unittest.mock import patch, MagicMock

from metadata_manager.models.methods.infilling_methods import (
    InfillingMethod,
    InfillingMethodRegistry
)


class TestInfillingMethod(unittest.TestCase):
    def test_valid_method(self):
        """Test that valid arguments create a valid method."""
        method = InfillingMethod(
            method_id=1,
            name="method name",
            description="description",
            function_name="interpolation_function"
        )

        self.assertEqual(method.method_id, 1)
        self.assertEqual(method.name, "method name")
        self.assertEqual(method.description, "description")
        self.assertEqual(method.function_name, "interpolation_function")

    @parameterized.expand([
        ("test_zero", 0),
        ("test_negative", -1),
    ])
    def test_invalid_method_id(self, _, method_id):
        """Test that invalid method_id values are rejected."""
        with self.assertRaises(ValueError):
            InfillingMethod(
                method_id=method_id,
                name="method name",
                description="description",
                function_name="interpolation_function"
            )

    def test_invalid_name(self):
        """Test that empty names are rejected."""
        with self.assertRaises(ValueError):
            InfillingMethod(
                method_id=1,
                name="",
                description="description",
                function_name="interpolation_function"
            )

    def test_call_method(self):
        """Test calling the method invokes the correct function with correct arguments."""
        mock_function = MagicMock(return_value="test_result")

        with patch('dritimeseriesprocessor.infilling.methods.linear_interpolation', mock_function):
            method = InfillingMethod(
                method_id=1,
                name="method name",
                description="description",
                function_name="linear_interpolation"
            )

            result = method(arg1="value1", arg2="value2")
            mock_function.assert_called_once_with(arg1="value1", arg2="value2")
            self.assertEqual(result, "test_result")

    def test_call_missing_function(self):
        """Test that calling a non-existent function raises ValueError."""
        method = InfillingMethod(
            method_id=1,
            name="Non-existent Method",
            description="This method doesn't exist",
            function_name="non_existent_function"
        )

        with self.assertRaises(ValueError):
            method()


class TestInfillingMethodRegistry(unittest.TestCase):
    def test_model_validate(self):
        """Test that model_validate correctly transforms and registers methods."""
        # Arrange
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
        registry = InfillingMethodRegistry.model_validate(test_data)
        self.assertEqual(set(registry.keys()), {"method1", "method2"})

    @patch("metadata_manager.models.methods.infilling_methods.InfillingMethod.model_validate")
    def test_validate_called_for_each_method(self, mock_validate):
        """Test that InfillingMethod.model_validate is called for each method."""
        mock_method = MagicMock(spec=InfillingMethod)
        mock_validate.return_value = mock_method

        test_data = {
            "method1": {"id": 1, "name": "Method 1", "description": "Description 1", "function_name": "func1"},
            "method2": {"id": 2, "name": "Method 2", "description": "Description 2", "function_name": "func2"},
            "method3": {"id": 3, "name": "Method 3", "description": "Description 3", "function_name": "func3"}
        }

        registry = InfillingMethodRegistry.model_validate(test_data)
        self.assertEqual(mock_validate.call_count, 3)

    def test_empty_data(self):
        """Test that empty data results in an empty registry."""
        test_data = {}
        registry = InfillingMethodRegistry.model_validate(test_data)
        self.assertEqual(len(registry), 0)

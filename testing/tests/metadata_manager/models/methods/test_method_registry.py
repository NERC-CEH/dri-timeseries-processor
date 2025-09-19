from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

from metadata_manager.models.common import ComponentType
from metadata_manager.models.methods.method_registry import InfillingMethods, Method, QcMethods


class TestMethod:
    @property
    def method_dict(self) -> Dict[str, str]:
        method_dict = {
            "method_type": "correction",
            "name": "method name",
            "description": "description",
            "id": 1,
            "function_name": "a_function_name",
        }
        return method_dict

    def test_valid_method(self) -> None:
        """Test that valid arguments create a valid method."""
        method = Method.model_validate(self.method_dict)

        assert method.method_id == 1
        assert method.method_type == ComponentType.CORRECTION
        assert method.name == "method name"
        assert method.description == "description"
        assert method.function_name == "a_function_name"

    @pytest.mark.parametrize(
        "method_id",
        [
            (0),
            (-1),
        ],
        ids=["test_zero", "test_negative"],
    )
    def test_invalid_method_id(self, method_id: int) -> None:
        """Test that invalid method_id values are rejected."""
        method_dict = self.method_dict.copy()
        method_dict["id"] = method_id
        with pytest.raises(ValueError):
            Method.model_validate(method_dict)

    def test_invalid_name(self) -> None:
        """Test that empty names are rejected."""
        method_dict = self.method_dict.copy()
        method_dict["name"] = ""

        with pytest.raises(ValueError):
            Method.model_validate(method_dict)

    def test_call_method(self) -> None:
        """Test calling the method invokes the correct function. Only valid with calculate/aggregation methods."""
        method_dict = self.method_dict.copy()
        method_dict["method_type"] = "calculate"
        method_dict["function_name"] = "NetRadiation"

        mock_function = MagicMock(return_value="test_result")
        with patch("dritimeseriesprocessor.deriving.derivations.NetRadiation", mock_function):
            method = Method.model_validate(method_dict)
            result = method(arg1="value1", arg2="value2")

            mock_function.assert_called_once_with(arg1="value1", arg2="value2")
            assert result == "test_result"

    def test_call_missing_function(self) -> None:
        """Test that calling a non-existent function raises ValueError."""
        method_dict = self.method_dict.copy()
        method_dict["method_type"] = "calculate"
        method = Method.model_validate(method_dict)
        with pytest.raises(ValueError):
            method()


class TestMethodRegisters:
    @pytest.mark.parametrize(
        "registry_class,method_type",
        [
            (InfillingMethods, ComponentType.INFILLING),
            (QcMethods, ComponentType.QUALITY_CONTROL),
        ],
    )
    def test_model_validate(self, registry_class: object, method_type: str) -> None:
        """Test that model_validate correctly transforms and registers methods."""
        test_data = {
            "method1": {
                "id": 1,
                "name": "Method 1",
                "description": "Description of method 1",
                "function_name": "method_1",
            },
            "method2": {
                "id": 2,
                "name": "Method 2",
                "description": "Description of method 2",
                "function_name": "method_2",
            },
        }
        registry = registry_class.model_validate(test_data)

        assert set(registry.keys()) == {"method1", "method2"}
        assert registry["method1"].method_type == method_type
        assert registry["method2"].method_type == method_type

    @pytest.mark.parametrize(
        "registry_class",
        [
            InfillingMethods,
            QcMethods,
        ],
    )
    @patch("metadata_manager.models.methods.method_registry.Method.model_validate")
    def test_validate_called_for_each_method(self, mock_validate: MagicMock, registry_class: object) -> None:
        """Test that InfillingMethod.model_validate is called for each method."""
        mock_method = MagicMock(spec=Method)
        mock_validate.return_value = mock_method

        test_data = {
            "method1": {"id": 1, "name": "Method 1", "description": "Description 1", "function_name": "func1"},
            "method2": {"id": 2, "name": "Method 2", "description": "Description 2", "function_name": "func2"},
            "method3": {"id": 3, "name": "Method 3", "description": "Description 3", "function_name": "func3"},
        }

        registry_class.model_validate(test_data)
        assert mock_validate.call_count == 3

    @pytest.mark.parametrize(
        "registry_class",
        [
            InfillingMethods,
            QcMethods,
        ],
    )
    def test_empty_data(self, registry_class: object) -> None:
        """Test that empty data results in an empty registry."""
        test_data = {}

        registry = registry_class.model_validate(test_data)

        assert len(registry) == 0

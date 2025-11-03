from typing import Callable, Type

import pytest
from pydantic import BaseModel, ValidationError


def valid_parses(load_json_file: Callable, filename: str, model: Type[BaseModel]) -> BaseModel:
    """Generic helper to test that a JSON file parses successfully with a given Pydantic model.

    Args:
        load_json_file: Fixture that loads a JSON file as a Python dict.
        filename: Path to the JSON file to validate.
        model: The Pydantic model class to validate against.

    Raises:
        ValidationError: If Pydantic validation failes
        AssertionError: If the parsed model is empty.
    """
    data = load_json_file(filename)
    result = model.model_validate(data)

    assert result.meta is not None
    assert result.items is not None

    return result


def invalid_raises(load_json_file: Callable, filename: str, model: Type[BaseModel]) -> None:
    """Generic helper to test that an invalid JSON file raises error with a given Pydantic model.

    Args:
        load_json_file: Fixture that loads a JSON file as a Python dict.
        filename: Path to the JSON file to validate.
        model: The Pydantic model class to validate against.
    """
    data = load_json_file(filename)

    data = load_json_file(filename)
    with pytest.raises(ValidationError):
        model.model_validate(data)

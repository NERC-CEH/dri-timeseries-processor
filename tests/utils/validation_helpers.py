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
        ValidationError: If Pydantic validation fails
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
    with pytest.raises(ValidationError):
        model.model_validate(data)


def assert_pydantic_validation_error_cause(
    exception_info: pytest.ExceptionInfo[ValidationError],
    expected_count: int,
    expected_type: str | list[str],
    expected_loc: tuple | list[tuple] | None = None,
) -> None:
    """Assert details of a Pydantic ValidationError.

    Args:
        exception_info: The ValidationError instance caught via pytest.raises.
        expected_count: Expected total number of errors.
        expected_type: Expected error type.
        expected_loc: Optional expected location tuple.
    """
    if isinstance(expected_type, str):
        expected_type = [expected_type]

    if isinstance(expected_loc, tuple):
        expected_loc = [expected_loc]

    errors = exception_info.value.errors()

    assert len(errors) == expected_count

    for idx, e in enumerate(errors):
        assert e["type"] == expected_type[idx]
        if expected_loc is not None:
            assert e["loc"] == expected_loc[idx]

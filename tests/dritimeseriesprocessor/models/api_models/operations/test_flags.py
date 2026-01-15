from typing import Any

import pytest
from tests.utils.fixture_helpers import discover_json_test_cases, load_json_file
from tests.utils.validation_helpers import invalid_raises

from dritimeseriesprocessor.models.api_models.flags import CoreFlagItem, CoreFlagResponse


class TestCoreFlagResponse:
    @pytest.mark.parametrize("filename", discover_json_test_cases("api_json/valid/operations/flags"))
    def test_valid_dataset(self, filename: str) -> None:
        data = load_json_file(filename)
        result = CoreFlagResponse.model_validate(data)
        assert result.core_flags is not None

    @pytest.mark.parametrize(
        "filename",
        discover_json_test_cases("api_json/invalid/operations/flags"),
    )
    def test_invalid_dataset(self, filename: str) -> None:
        invalid_raises(load_json_file, filename, CoreFlagResponse)


class TestCoreFlagItem:
    @pytest.mark.parametrize(
        "name,description,flag_id",
        [
            ("Test flag", "Tests the tests", 1),
            ("Test flag", "Tests the tests", 2),
            ("Test flag", "Tests the tests", 16),
            ("Test flag", "Tests the tests", 128),
        ],
    )
    def test_valid_core_flag(self, name: str, description: str, flag_id: int) -> None:
        """Test that a valid CoreFlag instance is created correctly.
        Also testing valid id's do not raise errors.
        """
        core_flag = CoreFlagItem(name=name, description=description, id=flag_id)
        assert core_flag.name == name
        assert core_flag.description == description
        assert core_flag.id == flag_id

    @pytest.mark.parametrize("bad_id", [-2, 0, 21, 6])
    def test_bad_id(self, bad_id: int) -> None:
        with pytest.raises(ValueError):
            CoreFlagItem(name="Test flag", description="Tests the tests", id=bad_id)

    @pytest.mark.parametrize("bad_id", [1.5, "ID", None])
    def test_id_non_int_invalid(self, bad_id: Any) -> None:
        with pytest.raises(ValueError):
            CoreFlagItem(name="Test flag", description="Tests the tests", id=bad_id)

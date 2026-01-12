import os
from typing import Iterator

import pytest

from dritimeseriesprocessor.utils.enums import Environment
from dritimeseriesprocessor.utils.environment import detect_environment


@pytest.fixture
def restore_environment() -> Iterator[None]:
    original = os.environ.get("environment")
    yield
    if original is None:
        os.environ.pop("environment", None)
    else:
        os.environ["environment"] = original


class TestDetectEnvironment:
    def test_default_environment_is_local(self, restore_environment: None) -> None:
        """Test that when no environment provided, it defaults to local"""
        os.environ.pop("environment", None)
        assert detect_environment() == Environment("local")

    @pytest.mark.parametrize("env", [e.value for e in Environment])
    def test_detect_each_valid_environment(self, env: str, restore_environment: None) -> None:
        """Test that all the valid environments are detected"""
        os.environ["environment"] = env
        assert detect_environment() == Environment(env)

    def test_invalid_environment_raises_value_error(self, restore_environment: None) -> None:
        """Test that an invalid environment name raises an error"""
        os.environ["environment"] = "INVALID"
        with pytest.raises(ValueError):
            detect_environment()

    def test_environment_is_case_sensitive(self, restore_environment: None) -> None:
        """Enum expects environment to be lowercase"""
        os.environ["environment"] = "LOCAL"
        with pytest.raises(ValueError):
            detect_environment()

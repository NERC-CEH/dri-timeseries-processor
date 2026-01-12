import os

import pytest
from config import ConfigFormatError

from dritimeseriesprocessor.configuration.app_config import AppConfigLive, AppConfigLocal, app_config
from dritimeseriesprocessor.utils.enums import Environment
from utils.fixture_helpers import TEST_DATA_ASSETS_INVALID, TEST_DATA_ASSETS_VALID, discover_file_test_cases

LIVE_ENVIRONMENTS = ["staging", "production", "staging-fake"]

REQUIRED_LOCAL_CONFIG_KEYS = [
    "metadata_api_url",
    "endpoint_url",
    "pushgateway_url",
]

REQUIRED_LOCAL_ENV_KEYS = [
    "AWS_ACCESS_KEY_ID",
    "AWS_DEFAULT_REGION",
    "AWS_SECRET_ACCESS_KEY",
]

REQUIRED_LIVE_CONFIG_KEYS = [
    "AWS_DEFAULT_REGION",
    "metadata_api_url",
    "pushgateway_url",
]


def patch_local(filename: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("environment", "local")
    monkeypatch.setattr("dritimeseriesprocessor.configuration.app_config.LOCAL_CONFIG_PATH", filename)


def patch_live(env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    if env == "local":
        raise Exception("Environment can't be 'local' when patching for live environment.")
    monkeypatch.setenv("environment", env)

    # set required environment variables
    for key in REQUIRED_LIVE_CONFIG_KEYS:
        monkeypatch.setenv(key, f"value_{key}")


class TestAppConfig:
    @pytest.mark.parametrize("filename", discover_file_test_cases(TEST_DATA_ASSETS_VALID))
    def test_local_config(self, filename: str, monkeypatch: pytest.MonkeyPatch) -> None:
        patch_local(filename, monkeypatch)

        cfg = AppConfigLocal(Environment.LOCAL)

        # check that class attributes have been set
        for key in REQUIRED_LOCAL_CONFIG_KEYS + REQUIRED_LOCAL_ENV_KEYS:
            assert cfg.__getattribute__(key) == f"value_{key}"

        # check that environment variables have been set
        for key in REQUIRED_LOCAL_ENV_KEYS:
            assert os.environ[key] == f"value_{key}"

    @pytest.mark.parametrize("env", LIVE_ENVIRONMENTS)
    def test_live_config(self, env: str, monkeypatch: pytest.MonkeyPatch) -> None:
        patch_live(env, monkeypatch)

        cfg = AppConfigLive(Environment(env))

        # check that class attributes have been set
        for key in REQUIRED_LIVE_CONFIG_KEYS:
            assert cfg.__getattribute__(key) == f"value_{key}"

    @pytest.mark.parametrize("filename", discover_file_test_cases(TEST_DATA_ASSETS_INVALID / "missing_keys"))
    def test_local_config_invalid_missing_keys(self, filename: str, monkeypatch: pytest.MonkeyPatch) -> None:
        patch_local(filename, monkeypatch)

        with pytest.raises(KeyError):
            AppConfigLocal(Environment.LOCAL)

    @pytest.mark.parametrize("filename", discover_file_test_cases(TEST_DATA_ASSETS_INVALID / "corrupt"))
    def test_local_config_invalid_corrupt_file(self, filename: str, monkeypatch: pytest.MonkeyPatch) -> None:
        patch_local(filename, monkeypatch)

        with pytest.raises(ConfigFormatError):
            AppConfigLocal(Environment.LOCAL)

    def test_app_config_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        filename = TEST_DATA_ASSETS_VALID / "env_local.cfg"
        patch_local(filename, monkeypatch)
        cfg = app_config()
        assert isinstance(cfg, AppConfigLocal)

    @pytest.mark.parametrize("env", LIVE_ENVIRONMENTS)
    def test_app_config_live(self, env: str, monkeypatch: pytest.MonkeyPatch) -> None:
        patch_live(env, monkeypatch)
        cfg = app_config()
        assert isinstance(cfg, AppConfigLive)

    @pytest.mark.parametrize("env", LIVE_ENVIRONMENTS)
    def test_local_config_invalid_env(self, env: str) -> None:
        with pytest.raises(EnvironmentError):
            AppConfigLocal(Environment(env))

    def test_live_config_invalid_env(self) -> None:
        with pytest.raises(EnvironmentError):
            AppConfigLive(Environment.LOCAL)

"""
Configuration module for the processing pipeline.

This module provides an interface for loading application configuration across different runtime environments.
Local development reads from an env.cfg file, while live environments source values directly from environment variables.

The `app_config()` function selects the appropriate configuration loader based on the detected environment.
"""

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

import config
from config import KeyNotFoundError

from new_processor.utils.enums import Environment
from new_processor.utils.environment import detect_environment

logger = logging.getLogger(__name__)

LOCAL_CONFIG_PATH = Path(__file__).parent.parent / "__assets__" / "env.cfg"


class AppConfig(ABC):
    """Base interface for all configuration sources."""

    # Required keys
    AWS_DEFAULT_REGION: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    endpoint_url: str
    level_0_bucket: str
    processed_bucket: str
    metadata_api_url: str
    environment: Environment

    def __init__(self):
        self.load_config()

    @abstractmethod
    def load_config(self) -> None:
        """Load the config"""


class AppConfigLocal(AppConfig):
    """Loads configuration values from different sources depending on the runtime environment.

    Check configs for missing or empty parameters and creates class instance attributes for each one.
    """

    def __init__(self, env: Environment):
        if env is not Environment.LOCAL:
            raise EnvironmentError(f"Environment must be set to 'local'. Got: '{env}'")
        super().__init__()

    def load_config(self) -> None:
        """Load config from env.cfg for local development.

        AWS credential values are exported into the environment to ensure that local components relying on boto3,
        SQS consumers, or DuckDB S3 access can function.
        """
        try:
            cfg = config.Config(str(LOCAL_CONFIG_PATH))
        except config.ConfigFormatError as err:
            logger.error(f"Problem with local env.cfg file: {str(err)}")
            raise

        try:
            self.AWS_DEFAULT_REGION = cfg["AWS_DEFAULT_REGION"]
            self.AWS_ACCESS_KEY_ID = cfg["AWS_ACCESS_KEY_ID"]
            self.AWS_SECRET_ACCESS_KEY = cfg["AWS_SECRET_ACCESS_KEY"]

            self.level_0_bucket = cfg["level_0_bucket"]
            self.processed_bucket = cfg["processed_bucket"]
            self.metadata_api_url = cfg["metadata_api_url"]
            self.endpoint_url = cfg["endpoint_url"]

            self.environment = Environment.LOCAL

        except KeyNotFoundError as err:
            raise KeyError(f"Missing required local config key:\n{err}")

        # Set AWS config params as env variables for sqs consumer to run locally
        os.environ["AWS_ACCESS_KEY_ID"] = cfg["AWS_ACCESS_KEY_ID"]
        os.environ["AWS_SECRET_ACCESS_KEY"] = cfg["AWS_SECRET_ACCESS_KEY"]
        os.environ["AWS_DEFAULT_REGION"] = cfg["AWS_DEFAULT_REGION"]


class AppConfigLive(AppConfig):
    """Loads configuration values for live environments."""

    def __init__(self, env: Environment):
        if env is Environment.LOCAL:
            raise EnvironmentError("Environment must not be set to 'local'.")
        super().__init__()

    def load_config(self) -> None:
        """Load config directly from environment variables.

        This mode is used for staging, production, and staging-fake environments (usually running within k8s).
        Configuration values are read directly from the environment and stored as instance attributes.
        """
        try:
            self.AWS_DEFAULT_REGION = os.environ["AWS_DEFAULT_REGION"]
            self.level_0_bucket = os.environ["level_0_bucket"]
            self.processed_bucket = os.environ["processed_bucket"]
            self.metadata_api_url = os.environ["metadata_api_url"]
            self.environment = Environment(os.environ["environment"])

        except KeyError as err:
            raise KeyError(f"Missing required live config key:\n{err}")


def app_config() -> AppConfig:
    """Loads configuration and caches."""
    env = detect_environment()
    if env is Environment.LOCAL:
        return AppConfigLocal(env)
    else:
        return AppConfigLive(env)

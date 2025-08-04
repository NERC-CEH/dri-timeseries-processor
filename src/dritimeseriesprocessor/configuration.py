"""Load and validate the configuration file.

This module handles loading config parameters for both local, staging and
production development.

Attributes:
    local_config_parameters: Expected local config parameters.
    kubernetes_config_parameters: Expected staging/production config parameters.

Note:
    When changing env.cfg update the attributes above and the manifest in
    the kubernetes cluster.
"""

import logging
import os
from pathlib import Path

import config

logger = logging.getLogger(__name__)

# Expected config values for validation
shared_config_parameters = ["AWS_DEFAULT_REGION", "level_0_bucket", "processed_bucket", "metadata_api_url"]

local_config_parameters = shared_config_parameters + [
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "endpoint_url",
]

kubernetes_config_parameters = shared_config_parameters + ["environment"]


class Configuration:
    """Configuartion for the time series processing app.

    Check config file for missing or empty parameters and
    creates attributes for each one.
    """

    def __init__(self):
        # Populate class attributes
        if "environment" not in os.environ:
            logger.info("Loading local config")
            setattr(Configuration, "environment", "local")

            # Load config, raise error if not formatted correctly
            # including empty parameters
            try:
                cfg = config.Config(str(Path(Path(__file__).parents[0], "__assets__", "env.cfg")))
            except config.ConfigFormatError as cfe:
                logger.error(cfe)
                raise

            # Check all expected config parameters exist
            # Add to class attributes
            for item in local_config_parameters:
                if item in cfg:
                    setattr(Configuration, item, cfg[item])
                else:
                    raise KeyError(f"{item}: doesn't exist in the config file.")

            # Also need to set AWS config params as env variables for sqs
            # consumer to run locally
            os.environ["AWS_ACCESS_KEY_ID"] = cfg["AWS_ACCESS_KEY_ID"]
            os.environ["AWS_SECRET_ACCESS_KEY"] = cfg["AWS_SECRET_ACCESS_KEY"]
            os.environ["AWS_DEFAULT_REGION"] = cfg["AWS_DEFAULT_REGION"]

        elif os.environ["environment"] in ["staging", "production", "staging-fake"]:
            logger.info(f"Loading {os.environ['environment']} config")
            for item in kubernetes_config_parameters:
                if item in os.environ:
                    setattr(Configuration, item, os.environ[item])
                else:
                    raise KeyError(f"{item}: doesn't exist in the manifest.")
        else:
            raise ValueError(
                """environment config must be \
                either 'staging' or 'production'"""
            )


app_config = Configuration()

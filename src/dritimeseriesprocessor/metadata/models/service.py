import asyncio
import json
from enum import Enum
from pathlib import Path
from typing import Optional, Union

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.metadata import api_manager
from dritimeseriesprocessor.metadata.models.configs.infilling import InfillingProcessConfigs
from dritimeseriesprocessor.metadata.models.methods.infilling_methods import InfillingMethodRegistry


class ConfigType(Enum):
    INFILLING = "infilling"
    CORRECTION = "correction"  # placeholder for moving other configs across


def load_config(config_type: Union[ConfigType, str]) -> Optional[InfillingProcessConfigs]:
    """Load configuration data based on the given configuration type.

    Args:
        config_type: The type of configuration to load.

    Returns:
        The parsed configurations.
    """
    if isinstance(config_type, str):
        config_type = ConfigType(config_type)

    if config_type == ConfigType.INFILLING:
        # TODO: To decide how to filter down (and at what stage to filter).  E.g. do we provide this function with
        #         a network name, and/or site name, and/or infilling method?
        metadata = api_manager.MetadataAPIManager(host=app_config.metadata_api_url, network="cosmos")
        data = asyncio.run(metadata.fetch_infill_configs())
        return InfillingProcessConfigs.model_validate(data)


def load_methods(config_type: Union[ConfigType, str]) -> Optional[InfillingMethodRegistry]:
    """Load method definitions based on the given configuration type.

    Args:
        config_type: The type of configuration methods to load.

    Returns:
        The parsed methods.
    """
    if isinstance(config_type, str):
        config_type = ConfigType(config_type)

    if config_type == ConfigType.INFILLING:
        with open(Path(__file__).parent.absolute() / "methods" / "infilling_methods.json", "r") as f:
            data = json.load(f)
        return InfillingMethodRegistry.model_validate(data)

import asyncio
import json
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Union

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.metadata import api_manager
from dritimeseriesprocessor.metadata.models.configs.infilling import InfillingConfig, InfillingProcessConfigs
from dritimeseriesprocessor.metadata.models.methods.infilling_methods import InfillingMethodRegistry
from dritimeseriesprocessor.metadata.models.time_series import TimeSeriesMetadataResponse


class ConfigType(Enum):
    INFILLING = "infilling"
    CORRECTION = "correction"  # placeholder for moving other configs across


def load_config(config_type: Union[ConfigType, str]) -> Optional[Dict[str, Dict[str, InfillingConfig]]]:
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
        infilling_configs = InfillingProcessConfigs.model_validate(data)

        # Add in the time-series metadata.
        # TODO: Might not need to do this as might include this info in the config api view.
        #   In which case, this dictionary can be built in the InfillingProcessConfigs object.
        result = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for config in infilling_configs:
            site_id = config.site_id
            time_series_meta = load_timeseries(config.time_series_name)
            column = time_series_meta.column
            resolution = time_series_meta.measure.resolution

            result[site_id][resolution][column].append(config)

        return result


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


def load_timeseries(timeseries_id: Optional[str] = None) -> TimeSeriesMetadataResponse:
    """Load time series metadata from the API.

    Args:
        timeseries_id: Optional ID to fetch a specific time series

    Returns:
        The parsed time series metadata.
    """
    metadata = api_manager.MetadataAPIManager(host=app_config.metadata_api_url, network="cosmos")
    data = asyncio.run(metadata.fetch_timeseries_metadata(timeseries_id=timeseries_id))
    return TimeSeriesMetadataResponse.model_validate(data)

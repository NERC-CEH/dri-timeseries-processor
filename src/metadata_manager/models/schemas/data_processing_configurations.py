import re
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, field_validator, model_validator

from metadata_manager.models.common import URI_ID_EXTRACT_REGEX, get_interval_dates


class Annotation(BaseModel):
    """Represents a generic annotation parameter

    Attributes:
        name: The annotation name
        value: The annotation value
    """

    name: str
    value: Optional[Union[int, float, str]] = None

    @model_validator(mode="before")
    @classmethod
    def extract_param_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract annotation info from raw API data.

        Args:
            data: The raw input data dictionary.

        Returns:
            Processed annotation data.
        """
        result = {}
        result["name"] = re.match(URI_ID_EXTRACT_REGEX, data["property"]["@id"]).group(1)
        result["value"] = data["hasValue"]["value"]

        return result


class Parameter(BaseModel):
    """Represents a generic configuration parameter with a name and value/reference.

    Attributes:
        name: The parameter name
        value: The direct parameter value
    """

    name: str
    value: Optional[Union[int, float, str, time]] = None

    @model_validator(mode="before")
    @classmethod
    def extract_param_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameter information from raw API data.

        Args:
            data: The raw input data dictionary.

        Returns:
            Processed parameter data.
        """
        result = {}

        result["name"] = re.match(URI_ID_EXTRACT_REGEX, data["parameter"]["@id"]).group(1).replace("-", "_")

        # Extract value or reference
        has_value = data["hasValue"]
        if "value" in has_value:
            result["value"] = has_value["value"]
        if "valueReference" in has_value and "@id" in has_value["valueReference"]:
            result["value"] = has_value["valueReference"]["@id"]

        return result

    @field_validator("value")
    @classmethod
    def parse_value(cls, value: str) -> Union[None, int, float, str, time]:
        """Validate and convert the 'value' field to the appropriate type.

        This validator attempts to parse the input value into one of four types:
        - int: If the value is a numeric whole number
        - float: If the value is a numeric decimal number
        - time: If the value is a time string in "HH:MM:SS" format
        - str: As a fallback if the value doesn't match any other type

        Args:
            value: The input value to parse

        Returns:
            The parsed value in the appropriate type
        """
        if value is None:
            return value

        # Try to convert to numeric (int or float)
        try:
            potential_numeric = float(value)
            if potential_numeric.is_integer():
                return int(potential_numeric)
            # Fall back to float if not an integer
            return potential_numeric
        except (ValueError, TypeError):
            pass

        # Try to parse as a time
        try:
            if isinstance(value, time):
                return value
            potential_time = datetime.strptime(value, "%H:%M:%S").time()
            return potential_time
        except (ValueError, TypeError):
            pass

        # Fall back to string representation
        return str(value)


class ConfigItem(BaseModel):
    """Represents a generic configuration item with methods, interval dates, and parameters.

    Attributes:
        name: The configuration name
        interval: To specify the period during which the configuration is/was applied
        observation_interval: To specify the range of observations in the dataset that the configuration applies to
        parameters: Dictionary of configuration parameters, keyed by parameter name
    """

    name: str
    interval: Tuple[datetime, Union[datetime, None]]
    observation_interval: Tuple[datetime, Union[datetime, None]]
    parameters: Dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def extract_config_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract configuration information for configuration from raw API data.

        Args:
            data: Raw configuration data from the API.

        Returns:
            Processed configuration data.
        """
        result = {}
        result["name"] = re.match(URI_ID_EXTRACT_REGEX, data["method"]["@id"]).group(1)

        # Get the interval dates
        result["interval"] = get_interval_dates(data.get("interval"))
        result["observation_interval"] = get_interval_dates(data.get("observationInterval"))

        # Extract parameters
        params = {}
        for arg in data.get("argument", []):
            param = Parameter.model_validate(arg)

            # Some arguments have the same names, e.g. in "error code" QC test, there could be multiple "value"
            # arguments.  Therefore, need to handle this here - make the dictionary value a list of all values found
            # with the same name.
            if param.name not in params:
                params[param.name] = param.value
            else:
                if not isinstance(params[param.name], list):
                    params[param.name] = [params[param.name]]
                params[param.name].append(param.value)

        result["parameters"] = params

        return result


class DataProcessingConfiguration(BaseModel):
    """Information for a specific data processing configuration applied to a time series.

    Attributes:
        site_id: Name of the site the config is applied to
        ts_id: Time series identifier
        configs: A list of the configuration details.  Usually there is only one, but there can be multiple
                 if different methods used at different points in the time series. Use start and end date to
                 determine which method is used at a given point in time.
    """

    site_id: str
    ts_id: str
    annotations: Dict[str, Any]
    configs: List[ConfigItem]

    @model_validator(mode="before")
    @classmethod
    def extract_config_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract infilling configuration information from raw API data.

        Parses the input data to extract the site identifier, variable name, processing priority,
        and associated configuration details.

        Args:
            Raw infilling configuration data from the API.

        Returns:
            Processed infilling configuration data.
        """
        result = {}

        result["site_id"] = data["appliesToTimeSeries"][0]["originatingSite"]["@id"]
        result["ts_id"] = data["appliesToTimeSeries"][0]["@id"]

        annotation_dict = {}
        for annotation_data in data.get("hasAnnotation", []):
            annotation = Annotation.model_validate(annotation_data)
            annotation_dict[annotation.name] = annotation.value
        result["annotations"] = annotation_dict

        configs = [ConfigItem.model_validate(config) for config in data["hasCurrentConfiguration"]]
        if len(configs) == 0:
            raise ValueError("Expect at least one method configuration, but found none.")
        result["configs"] = configs

        return result


class DataProcessingConfigurations(List[DataProcessingConfiguration]):
    """List of data processing configurations for a time series."""

    @classmethod
    def model_validate(cls, data: Any) -> "DataProcessingConfigurations":
        """Parse API data processing configuration data into a list of configuration model items.

        Args:
            data: Raw API data which can be a dictionary containing an "items" key or a list of configuration items.

        Returns:
            A list of configuration model items, each of which is a subclass of DataProcessingConfiguration.
        """
        if isinstance(data, dict):
            items = data["items"]
        elif isinstance(data, list):
            items = data
        else:
            items = []

        configs = [DataProcessingConfiguration.model_validate(item) for item in items]
        return cls(configs)

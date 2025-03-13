import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, ValidationInfo, field_validator, model_validator

from dritimeseriesprocessor.metadata.models.time_series import TimeSeriesMetadata


class Annotation(BaseModel):
    """ Represents a generic annotation parameter

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

        regex = r".*\/(.+)"
        result["name"] = re.match(regex, data["property"]["@id"]).group(1)
        result["value"] = data["hasValue"]["value"]

        return result


class Parameter(BaseModel):
    """Represents an infilling method's configuration parameter with a name and value/reference.

    Attributes:
        name: The parameter name
        value: The direct parameter value
        value_reference: A reference to another configuration item
    """
    name: str
    value: Optional[Union[int, float, str]] = None
    value_reference: Optional[str] = None

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

        regex = r".*\/(.+)"
        result["name"] = re.match(regex, data["parameter"]["@id"]).group(1).replace("-", "_")

        # Extract value or reference
        has_value = data["hasValue"]
        if "value" in has_value:
            result["value"] = has_value["value"]
        if "valueReference" in has_value and "@id" in has_value["valueReference"]:
            result["value"] = has_value["valueReference"]["@id"]

        return result


class MethodConfigItem(BaseModel):
    """Represents an infilling configuration item with method, dates, and parameters (specific to the method).

    Attributes:
        method: The interpolation or data processing method
        start_date: When this configuration becomes active
        end_date: When this configuration ends (optional)
        parameters: Dictionary of configuration parameters, keyed by parameter name
    """

    name: str
    start_date: datetime
    end_date: Optional[datetime] = None
    parameters: Dict[str, Any]

    @field_validator("end_date", mode="after")
    @classmethod
    def validate_end_date(cls, end_date: Optional[datetime], info: ValidationInfo) -> Optional[datetime]:
        """Validate that end_date is after start_date (if provided).

        Args:
            end_date: The end_date value to validate.
            info: Provides the other fields of the metadata (including the start_date).

        Raises:
            ValueError: If end_date is provided and is not later than start_date.

        Returns:
            The validated end_date value.
        """
        if end_date is not None:
            start_date = info.data.get("start_date")
            if start_date and end_date <= start_date:
                raise ValueError(f"end_date [{end_date}] must be after start_date [{start_date}]")
        return end_date

    @model_validator(mode="before")
    @classmethod
    def extract_config_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract configuration information for infill methods from raw API data.

        Parses the input to extract the infill method name, observation interval dates, and parameters for the method.

        Args:
            data: Raw configuration data from the API.

        Returns:
            Processed configuration data.
        """
        result = {}

        # Extract method name from URL
        result["name"] = data["method"]["@id"].split("/")[-1]

        # Extract dates from observation interval
        interval = data["observationInterval"]
        if "startDate" in interval:
            result["start_date"] = interval["startDate"]
        if "endDate" in interval:
            result["end_date"] = interval["endDate"]

        # Extract parameters
        params = {}
        for arg in data["argument"]:
            param = Parameter.model_validate(arg)
            params[param.name] = param.value
        result["parameters"] = params

        return result


class InfillingConfig(BaseModel):
    """Configuration for a specific infilling method for a time series variable.

    Attributes:
        site_id: Identifier for the site/facility
        variable: Name of the time series variable
        priority: Processing priority
        configuration: The configuration details
    """

    site_id: str
    variable: TimeSeriesMetadata
    priority: int
    method: MethodConfigItem

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

        # Extract site_id
        regex = r".*\/\w+-(\w+)"
        result["site_id"] = re.match(regex, data["appliesToFacility"][0]["@id"]).group(1).upper()

        # Extract time series variable info
        regex = r".*\/(.+)"
        variable_name = re.match(regex, data["appliesToTimeSeries"][0]["@id"]).group(1)
        # hopefully this info will be bought into the config response, rather than having to do a separate api call
        # need a local import to avoid circular import.  hopefully won't need this after above is done.
        from dritimeseriesprocessor.metadata.models.service import load_timeseries
        variable_meta = load_timeseries(variable_name)
        result["variable"] = variable_meta

        # Extract annotations from hasAnnotation, and get the priority value
        annotation_dict = {}
        for annotation_data in data["hasAnnotation"]:
            annotation = Annotation.model_validate(annotation_data)
            annotation_dict[annotation.name] = annotation.value
        result["priority"] = annotation_dict["data-processing-configuration-priority"]

        # Extract infilling method info
        current_config = data["hasCurrentConfiguration"]
        if len(current_config) != 1:
            # TODO: verify this is expected - only one hasCurrentConfiguration per InternalDataProcessingConfiguration
            raise UserWarning(f"Unexpected number of infilling configurations found in {data}")
        method_config = MethodConfigItem.model_validate(current_config[0])
        result["method"] = method_config

        return result


class InfillingProcessConfigs(Dict[str, Dict[str, InfillingConfig]]):
    """Dictionary of infilling configurations for time series, indexed by variable name."""

    @classmethod
    def model_validate(cls, data: Any) -> "InfillingProcessConfigs":
        """Parse API data into a dictionary of variable name to configuration mappings.

        Args:
            data: Raw API data which can be a dictionary containing an "items" key or a list of configuration items.

        Returns:
            A dictionary with variable names as keys and InfillingConfig instances as values.
        """
        result = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

        if isinstance(data, dict) and "items" in data:
            items = data["items"]
        elif isinstance(data, list):
            items = data
        else:
            items = []

        for item in items:
            config = InfillingConfig.model_validate(item)
            site_id = config.site_id
            column = config.variable.column
            resolution = config.variable.measure.resolution

            result[site_id][resolution][column].append(config)

        return cls(result)

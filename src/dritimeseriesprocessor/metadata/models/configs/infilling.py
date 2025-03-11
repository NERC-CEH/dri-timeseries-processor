from datetime import datetime
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, ValidationInfo, field_validator, model_validator


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

        This function extracts the parameter name and its associated value or reference.

        Args:
            data: The raw input data dictionary.

        Returns:
            Processed parameter data.
        """
        if isinstance(data, dict):
            if "parameter" in data and "hasValue" in data:
                # Extract parameter name from the URL
                param_id = data["parameter"]["@id"]
                data["name"] = param_id.split("/")[-1]

                # Extract value or reference
                has_value = data["hasValue"]
                if "value" in has_value:
                    data["value"] = has_value["value"]
                if "valueReference" in has_value and "@id" in has_value["valueReference"]:
                    data["value_reference"] = has_value["valueReference"]["@id"]
        return data


class ConfigItem(BaseModel):
    """Represents an infilling configuration item with method, dates, and parameters (specific to the method).

    Attributes:
        method: The interpolation or data processing method
        start_date: When this configuration becomes active
        end_date: When this configuration ends (optional)
        parameters: Dictionary of configuration parameters, keyed by parameter name
    """

    method: str
    start_date: datetime
    end_date: Optional[datetime] = None
    parameters: Dict[str, Parameter]

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

        if isinstance(data, dict):
            # Extract method name from URL
            if "method" in data:
                result["method"] = data["method"]["@id"].split("/")[-1]

            # Extract dates from observation interval
            if "observationInterval" in data:
                interval = data["observationInterval"]
                if "startDate" in interval:
                    result["start_date"] = interval["startDate"]
                if "endDate" in interval:
                    result["end_date"] = interval["endDate"]

            # Extract parameters
            params = {}
            if "argument" in data:
                for arg in data["argument"]:
                    param = Parameter.model_validate({"parameter": arg["parameter"], "hasValue": arg["hasValue"]})
                    params[param.name] = param
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
    variable: str
    priority: int
    configuration: ConfigItem

    @model_validator(mode="before")
    @classmethod
    def extract_timeseries_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract time series configuration information from raw API data.

        Parses the input data to extract the site identifier, variable name, processing priority,
        and associated configuration details.

        Args:
            Raw time series configuration data from the API.

        Returns:
            Processed infilling configuration data.
        """
        result = {}

        if isinstance(data, dict):
            # Extract site_id
            if "appliesToFacility" in data and data["appliesToFacility"]:
                facility_id = data["appliesToFacility"][0]["@id"]
                result["site_id"] = facility_id.split("/")[-1]

            # Extract variable name
            if "appliesToTimeSeries" in data and data["appliesToTimeSeries"]:
                ts_id = data["appliesToTimeSeries"][0]["@id"]
                result["variable"] = ts_id.split("/")[-1]

            # Extract priority from hasAnnotation
            if "hasAnnotation" in data and data["hasAnnotation"]:
                for annotation in data["hasAnnotation"]:
                    if "property" in annotation and "hasValue" in annotation:
                        prop_id = annotation["property"]["@id"]
                        if prop_id.endswith("data-processing-configuration-priority"):
                            result["priority"] = annotation["hasValue"]["value"]

            # Extract configuration info
            if "hasCurrentConfiguration" in data and data["hasCurrentConfiguration"]:
                result["configuration"] = ConfigItem.model_validate(data["hasCurrentConfiguration"][0])

        return result


class InfillingProcessConfigs(Dict[str, InfillingConfig]):
    """Dictionary of infilling configurations for time series, indexed by variable name."""

    @classmethod
    def model_validate(cls, data: Any) -> "InfillingProcessConfigs":
        """Parse API data into a dictionary of variable name to configuration mappings.

        Args:
            data: Raw API data which can be a dictionary containing an "items" key or a list of configuration items.

        Returns:
            A dictionary with variable names as keys and InfillingConfig instances as values.
        """
        result = cls()

        if isinstance(data, dict) and "items" in data:
            items = data["items"]
        elif isinstance(data, list):
            items = data
        else:
            items = []

        for item in items:
            config = InfillingConfig.model_validate(item)
            result[config.variable] = config

        return result

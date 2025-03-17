import re
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator

from metadata_manager.models.common import URI_ID_EXTRACT_REGEX


class Measure(BaseModel):
    """Processing time series measure information

    Attributes:
        units: The units of the time series
        resolution: The resolution value
        periodicity: The periodicity value
    """

    units: Optional[str]
    resolution: str
    periodicity: str

    @model_validator(mode="before")
    @classmethod
    def extract_measure_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract measure information from raw data.

        Args:
            data: The raw data dictionary containing measure details.

        Returns:
            A dictionary with the extracted measure information

        Raises:
            ValueError: If the 'prefLabel' in 'hasUnit' contains more than one element.
        """
        result = {}

        units = data["hasUnit"].get("prefLabel")
        if isinstance(units, list):
            if len(units) != 1:
                raise ValueError(f"Units must have 1 prefLabel: {units}")

        result["units"] = units[0] if units else None
        result["resolution"] = data["aggregation"]["resolution"]
        result["periodicity"] = data["aggregation"]["periodicity"]

        return result


class ProcessingLevel(BaseModel):
    """Processing level information

    Attributes:
        description: The description of the processing level
    """

    description: str

    @model_validator(mode="before")
    @classmethod
    def extract_processing_level_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract processing level information from raw data.

        Args:
           data: The raw data dictionary containing processing level details.

        Returns:
           A dictionary with the processing level description.

        Raises:
           ValueError: If the 'prefLabel' contains more than one element.
        """
        proc_level = data["prefLabel"]
        if isinstance(proc_level, list):
            if len(proc_level) != 1:
                raise ValueError(f"Processing level must have 1 prefLabel: {proc_level}")
            proc_level = proc_level[0]

        return {"description": proc_level}


class TimeSeriesMetadata(BaseModel):
    """Model for time series metadata

    Attributes:
        name: Name of time series
        description: Description of time series
        measure: Measure object containing units, resolution etc.
        processing_level: ProcessingLevel object
        bucket: Name of s3 bucket where time series data is saved
        dataset: Name of dataset in bucket
        column: Name of column this time series is referred to as in files
    """

    name: str
    description: str
    measure: Measure
    processing_level: ProcessingLevel
    bucket: str
    dataset: str
    column: str

    @model_validator(mode="before")
    @classmethod
    def extract_timeseries_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract time series information from raw API data.

        Args:
            data : Raw time series data from the API.

        Returns:
            Processed data.
        """
        result = {}

        result["name"] = re.match(URI_ID_EXTRACT_REGEX, data["@id"]).group(1)

        description = data["prefLabel"]
        if isinstance(description, list):
            if len(description) != 1:
                raise ValueError(f"Time-series must have 1 prefLabel: {description}")
        result["description"] = description[0]

        result["measure"] = Measure.model_validate(data["measure"])
        result["processing_level"] = ProcessingLevel.model_validate(data["processingLevel"])
        result["bucket"] = data["sourceBucket"]
        result["dataset"] = data["sourceDataset"]
        result["column"] = data["sourceColumnName"]

        return result


class TimeSeriesMetadataResponse(BaseModel):
    """Response wrapper that automatically extracts the single time series item"""

    item: TimeSeriesMetadata = Field(None)

    @classmethod
    def model_validate(cls, obj: Dict[str, Any], *args, **kwargs) -> TimeSeriesMetadata:
        """Validate and extract a single time series metadata item from the response.

        Args:
           obj: Dictionary containing the response with an "items" key.
           *args: Additional positional arguments (needed to match call to BaseModel.model_validate).
           **kwargs: Additional keyword arguments (needed to match call to BaseModel.model_validate).

        Returns:
           TimeSeriesMetadata: The validated time series metadata instance.

        Raises:
           ValueError: If the "items" list does not contain exactly one item.
        """
        if len(obj["items"]) != 1:
            raise ValueError(f"Expected exactly one item in the time series response, got {len(obj['items'])}")
        # Create a new dict with the single item
        return TimeSeriesMetadata.model_validate(obj["items"][0])

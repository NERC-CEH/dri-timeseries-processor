import re
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator

from metadata_manager.models.common import URI_ID_EXTRACT_REGEX, check_single_list_item


class Measure(BaseModel):
    """Processing time series measure information

    Attributes:
        measure_id: The ID of the measure
        units: The units of the time series
        resolution: The resolution value
        periodicity: The periodicity value
    """

    measure_id: str
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
        """
        result = {}

        result["measure_id"] = data["@id"]
        result["units"] = check_single_list_item(data["hasUnit"].get("prefLabel"))
        result["resolution"] = data["aggregation"]["resolution"]
        result["periodicity"] = data["aggregation"]["periodicity"]

        return result


class ProcessingLevel(BaseModel):
    """Processing level information

    Attributes:
        processing_level_id: The ID of the processing level
    """

    processing_level_id: str

    @property
    def processing_type(self) -> str:
        return re.match(URI_ID_EXTRACT_REGEX, self.processing_level_id).group(1)

    @model_validator(mode="before")
    @classmethod
    def extract_processing_level_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract processing level information from raw data.

        Args:
           data: The raw data dictionary containing processing level details.

        Returns:
           A dictionary with the processing level info.
        """
        return {"processing_level_id": data["@id"]}


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

        type_info = check_single_list_item(data["type"])

        result["name"] = re.match(URI_ID_EXTRACT_REGEX, data["@id"]).group(1)
        result["measure"] = Measure.model_validate(type_info["measure"])
        result["processing_level"] = ProcessingLevel.model_validate(type_info["processingLevel"])
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


class DependentTimeSeriesMetadata(BaseModel):
    ts_id: str
    name: str
    processing_level_id: str


class DependentTimeSeriesMetadataResponse(BaseModel):
    item: DependentTimeSeriesMetadata = Field(None)

    @classmethod
    def model_validate(cls, obj: Dict[str, Any], *args, **kwargs) -> DependentTimeSeriesMetadata:
        dependent_time_series_metadata = []
        for item in obj["items"]:
            type_info = check_single_list_item(item["type"])

            processing_level = ProcessingLevel.model_validate(type_info["processingLevel"])
            dependent_time_series_metadata.append(
                DependentTimeSeriesMetadata(
                    ts_id=item["@id"],
                    name=re.match(URI_ID_EXTRACT_REGEX, item["@id"]).group(1),
                    processing_level_id=processing_level.processing_type,
                )
            )
        return dependent_time_series_metadata


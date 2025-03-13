import re

from typing import Any, List, Dict, Optional
from pydantic import BaseModel, Field, model_validator


class Measure(BaseModel):
    """Processing time series measure information"""
    units: Optional[str]
    resolution: str
    periodicity: str

    @model_validator(mode="before")
    @classmethod
    def extract_measure_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        result = {}

        pref_label = data["hasUnit"].get("prefLabel")
        result["units"] = pref_label[0] if pref_label else None
        result["resolution"] = data["aggregation"]["resolution"]
        result["periodicity"] = data["aggregation"]["periodicity"]

        return result


class ProcessingLevel(BaseModel):
    """Processing level information"""
    description: List[str]

    @model_validator(mode="before")
    @classmethod
    def extract_processing_level_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"description": data["prefLabel"]}


class TimeSeriesMetadata(BaseModel):
    """Model for time series metadata"""
    name: str
    description: List[str]
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
            Raw time series data from the API.

        Returns:
            Processed data.
        """
        result = {}

        regex = r".*\/(.+)"
        result["name"] = re.match(regex, data["@id"]).group(1)
        result["description"] = data["prefLabel"]
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
    def model_validate(cls, obj, *args, **kwargs):
        if len(obj["items"]) != 1:
            raise ValueError(f"Expected exactly one item in the time series response, got {len(obj['items'])}")
        # Create a new dict with the single item
        return TimeSeriesMetadata.model_validate(obj["items"][0])

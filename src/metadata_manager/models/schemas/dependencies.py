import re
from typing import Any, Dict

from pydantic import BaseModel, Field, model_validator

from metadata_manager.models.common import URI_ID_EXTRACT_REGEX, check_single_list_item


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

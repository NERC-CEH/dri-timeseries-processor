from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator

from metadata_manager.models.common import get_property


class Measure(BaseModel):
    """Measure information

    Attributes:
        measure_id: The ID of the measure.
    """

    measure_id: str

    @model_validator(mode="before")
    @classmethod
    def extract_measure_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract measure information from raw data.

        Args:
            data: The raw data dictionary containing measure details.

        Returns:
            A dictionary with the measure info.
        """
        return {"measure_id": data["@id"]}


class Methodology(BaseModel):
    """Methodology information

    Attributes:
        derivation_id: The ID of the derivation process
        uses: the dependent time series definitions
        configuration_type: the processing method
    """

    derivation_id: str
    uses: list
    configuration_type: str

    @model_validator(mode="before")
    @classmethod
    def extract_methodology_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract methodology information from raw API data.

        Args:
            data : Raw methodlogy data from the API.

        Returns:
            Processed data.
        """
        result = {}
        uses = []

        result["derivation_id"] = get_property("@id", data)
        dependencies = data["uses"]
        for items in dependencies:
            uses.append(get_property("@id", items))
        result["uses"] = uses
        result["configuration_type"] = get_property("@id", get_property("type", get_property("configuration", data)))

        return result


class DerivationMetadata(BaseModel):
    """Processing time series methodology information

    Attributes:
        timeseries_def: The timeseires definition
        measure: Info on the measure
        methodology: Info on how the timeseries def is processed
    """

    timeseries_def: str
    measure: Measure
    methodology: Optional[Methodology] = None

    @model_validator(mode="before")
    @classmethod
    def extract_derivation_metadata_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract derivation_metadata information from raw API data.

        Args:
            data : Raw derivation metadata from the API.

        Returns:
            Processed data.
        """
        result = {}

        result["timeseries_def"] = data["@id"]
        result["measure"] = Measure.model_validate(data["measure"])
        if "methodology" in data:
            result["methodology"] = Methodology.model_validate(data["methodology"])

        return result


class TimeseriesDerivationResponse(BaseModel):
    """Response wrapper that automatically extracts the single time series item"""

    item: DerivationMetadata = Field(None)

    @classmethod
    def model_validate(cls, obj: Dict[str, Any], *args, **kwargs) -> DerivationMetadata:
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
        return DerivationMetadata.model_validate(obj["items"][0])

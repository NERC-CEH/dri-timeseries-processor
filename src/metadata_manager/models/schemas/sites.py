from typing import Any, Dict, List

from pydantic import BaseModel, Field, model_validator

from metadata_manager.models.common import get_property


class SiteMetadata(BaseModel):
    """Site metadata information

    Attributes:
        id: ID for the site (e.g. 'http://fdri.ceh.ac.uk/id/site/cosmos-alic1').
        altitude: The altitude of the site location.

    """

    id: str
    altitude: float

    @model_validator(mode="before")
    @classmethod
    def model_validate(cls, data: Dict[str, Any], *args, **kwargs) -> Dict[str, Any]:
        site_metadata = {"id": data["@id"], "altitude": data["altitude"]}
        return site_metadata


class SiteMetadataResponse(BaseModel):
    """Response wrapper that automatically extracts the single site metadata item"""

    item: SiteMetadata = Field(None)

    @classmethod
    def model_validate(cls, obj: Dict[str, Any], *args, **kwargs) -> SiteMetadata:
        """Validate and extract a single site metadata item from the response.

        Args:
            obj: Dictionary containing the response with an "items" key.
            *args: Additional positional arguments (needed to match call to BaseModel.model_validate).
            **kwargs: Additional keyword arguments (needed to match call to BaseModel.model_validate).

        Returns:
            SitesMetadata: The validated sites metadata instance.

        Raises:
            ValueError: If the "items" list does not contain exactly one item.

        """
        if len(obj["items"]) != 1:
            raise ValueError(f"Expected exactly one item in the site metadata response, got {len(obj['items'])}")

        # Create a new dict with the single item
        return SiteMetadata.model_validate(obj["items"][0])


class Sites(BaseModel):
    """Sites information.

    Attributes:
        site_list: list of sites
    """

    site_list: List[str]

    @model_validator(mode="before")
    @classmethod
    def extract_site_ids(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract site ids from raw API data.

        Args:
            data : Raw site metadata from the API.

        Returns:
            Processed data.
        """
        sites = []
        for site in data:
            sites.append(get_property("@id", site))

        return {"site_list": sites}


class SitesMetadata(BaseModel):
    """Model for sites metadata

    Attributes:
        network_id: The ID for the network
        sites: List of sites
        network_label: Friendly network name
    """

    network_id: str
    sites: Sites
    network_label: str

    @model_validator(mode="before")
    @classmethod
    def extract_site_metadata_info(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract site metadata information from raw API data.

        Args:
            data : Raw site metadata from the API.

        Returns:
            Processed data.
        """
        result = {}
        result["network_id"] = get_property("@id", data)
        result["sites"] = Sites.model_validate(data["contains"])
        result["network_label"] = get_property("label", data)

        return result


class SitesResponse(BaseModel):
    """Response wrapper that automatically extracts the single sites item"""

    item: SitesMetadata = Field(None)

    @classmethod
    def model_validate(cls, obj: Dict[str, Any], *args, **kwargs) -> SitesMetadata:
        """Validate and extract a single sites metadata item from the response.

        Args:
            obj: Dictionary containing the response with an "items" key.
            *args: Additional positional arguments (needed to match call to BaseModel.model_validate).
            **kwargs: Additional keyword arguments (needed to match call to BaseModel.model_validate).

        Returns:
            SitesMetadata: The validated sites metadata instance.

        Raises:
            ValueError: If the "items" list does not contain exactly one item.
        """
        if len(obj["items"]) != 1:
            raise ValueError(f"Expected exactly one item in the sites response, got {len(obj['items'])}")
        # Create a new dict with the single item
        return SitesMetadata.model_validate(obj["items"][0])

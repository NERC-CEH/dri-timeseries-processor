"""
Pydantic models for the Network metadata endpoint.

Example API call:
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/network/fdri.json

Represents the metadata for a **network** of sites as returned by the FDRI metadata API. The ``contains`` field
lists all sites associated with the network.
"""

from pydantic import Field

from new_processor.api_models.shared import BaseAPIResponse, IDModel


class Contain(IDModel):
    """Container specification with label."""

    label: list[str] = Field(..., alias="label")


class NetworkItem(IDModel):
    """Network item with containers and labels."""

    field_type: list[IDModel] = Field(..., alias="@type")
    contains: list[Contain]
    label: list[str]


class Network(BaseAPIResponse):
    """Network API response."""

    items: list[NetworkItem] = Field(..., max_length=1)

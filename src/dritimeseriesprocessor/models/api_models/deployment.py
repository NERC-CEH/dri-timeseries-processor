"""
Pydantic models for the Deployment metadata endpoint.

Example API call:
    https://dri-metadata-api.staging.eds.ceh.ac.uk/id/deployment?deployedOnPlatform=http://fdri.ceh.ac.uk/id/platform/cosmos-bunny-aws_anem

Represents the metadata for a **deployment** of instrumentation at a given site.
"""

from pydantic import Field

from dritimeseriesprocessor.models.api_models.shared import BaseAPIResponse, IDModel


class DeployedSystem(IDModel):
    serialNumber: int | str
    label: list[str]
    type: IDModel


class DeploymentItem(IDModel):
    """Deployment item with containers and labels."""

    field_type: list[IDModel] = Field(..., alias="@type")
    label: list[str]
    start_date: str = Field(..., alias="startedAtTime")
    end_date: str | None = Field(None, alias="endedAtTime")
    deployedHeight: float | None = None
    deployedSystem: list[DeployedSystem] = Field(default_factory=list)


class Deployment(BaseAPIResponse):
    """Deployment API response."""

    items: list[DeploymentItem]

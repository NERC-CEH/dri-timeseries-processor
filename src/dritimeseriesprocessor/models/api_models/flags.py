from pydantic import Field

from dritimeseriesprocessor.models.api_models.shared import BaseAPIResponse, IDModel


class FlagColumn(IDModel):
    column_name: str = Field(..., alias="columnName")
    value_scheme: IDModel = Field(..., alias="valueScheme")


class FlagSchemeMember(IDModel):
    """Individual member of a flag scheme"""

    pref_label: list[str] = Field(..., alias="prefLabel")
    value: int


class FlagScheme(IDModel):
    """A single flag scheme.

    hasTopConcept: contains the individual 'members' of this flag scheme.
    flagType: what flag columns using this scheme are for, e.g. `.../ref/common/flag_type/quality_control_flags`.
    """

    title: list[str]
    has_top_concept: list[FlagSchemeMember] = Field(..., alias="hasTopConcept")
    flag_type: IDModel = Field(..., alias="flagType")


class FlagSchemeResponse(BaseAPIResponse):
    """Flag Scheme API response."""

    items: list[FlagScheme]

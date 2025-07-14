from typing import List, Optional

from pydantic import BaseModel, Field


class IDModel(BaseModel):
    """Base model with ID.

    Attributes:
        id: The unique identifier for the model.
    """

    id: str = Field(..., alias="@id")


class Variable(IDModel):
    """Variable definition with ID and label.

    Attributes:
        pref_label: List of preferred labels for the variable.
    """

    pref_label: List[str] = Field(..., alias="prefLabel")


class Unit(IDModel):
    """Unit definition with ID and label.

    Attributes:
        pref_label: List of preferred labels for the unit.
    """

    pref_label: List[str] = Field(..., alias="prefLabel")


class Aggregation(IDModel):
    """Aggregation definition with statistic, periodicity and resolution.

    Attributes:
        value_statistic: The statistic used for value aggregation.
        periodicity: The time periodicity for aggregation.
        resolution: The resolution of the aggregation.
    """

    value_statistic: IDModel = Field(..., alias="valueStatistic")
    periodicity: str
    resolution: str


class Measure(IDModel):
    """Measure definition with variable, unit and aggregation.

    Attributes:
        variable: The variable being measured.
        has_unit: The unit of measurement.
        aggregation: The aggregation method used.
    """

    variable: Variable
    has_unit: Unit = Field(..., alias="hasUnit")
    aggregation: Aggregation


class TimeSeriesType(IDModel):
    """Type definition for time series data.

    Attributes:
        processing_level: The level of processing applied to the data.
        measure: The measure definition for the time series.
    """

    processing_level: IDModel = Field(..., alias="processingLevel")
    measure: Measure


class TimeSeriesDataset(IDModel):
    """Individual time series dataset.

    Attributes:
        type_ref: List of type references for the dataset.
        type: List of time series types.
        source_bucket: Optional source bucket identifier.
        source_dataset: Optional source dataset identifier.
        source_column_name: Optional source column name.
        originating_facility: Optional list of originating facilities.
        originating_site: List of originating sites.
    """

    type_ref: List[IDModel] = Field(..., alias="@type")
    type: List[TimeSeriesType]
    source_bucket: Optional[str] = Field(None, alias="sourceBucket")
    source_dataset: Optional[str] = Field(None, alias="sourceDataset")
    source_column_name: Optional[str] = Field(None, alias="sourceColumnName")
    originating_facility: Optional[List[IDModel]] = Field(None, alias="originatingFacility")
    originating_site: List[IDModel] = Field(..., alias="originatingSite")


class Meta(IDModel):
    """Metadata for the response.

    Attributes:
        publisher: The publisher of the data.
        license: The license identifier.
        license_name: The license name.
        comment: Additional comments about the data.
        version: The version of the data.
        has_format: List of available formats.
        limit: The limit on number of items returned.
    """

    publisher: str
    license: str
    license_name: str = Field(..., alias="licenseName")
    comment: str
    version: str
    has_format: List[str] = Field(..., alias="hasFormat")
    limit: int


class TimeseriesDatasetResponse(BaseModel):
    """Main response model for metadata dataset API.

    Attributes:
        meta: Metadata information for the response.
        items: List of time series datasets.
    """

    meta: Meta
    items: List[TimeSeriesDataset]

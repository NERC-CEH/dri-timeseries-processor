from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Union
from datetime import datetime


class BaseType(BaseModel):
    """Reference type with an ID"""
    id: str = Field(..., alias="@id")


class Variable(BaseType):
    """Variable definition with ID and label"""
    pref_label: List[str] = Field(..., alias="prefLabel")


class Unit(BaseType):
    """Unit definition with ID and label"""
    pref_label: List[str] = Field(..., alias="prefLabel")

class Aggregation(BaseType):
    """Aggregation definition with statistic, periodicity and resolution"""
    value_statistic: BaseType = Field(..., alias="valueStatistic")
    periodicity: str
    resolution: str


class Measure(BaseType):
    """Measure definition with variable, unit and aggregation"""
    variable: Variable
    has_unit: Unit = Field(..., alias="hasUnit")
    aggregation: Aggregation

class TimeSeriesType(BaseType):
    """Type definition for time series data"""
    processing_level: BaseType = Field(..., alias="processingLevel")
    measure: Measure

class TimeSeriesDataset(BaseType):
    """Individual time series dataset"""
    type_ref: List[BaseType] = Field(..., alias="@type")
    type: List[TimeSeriesType]
    source_bucket: str = Field(..., alias="sourceBucket")
    source_dataset: str = Field(..., alias="sourceDataset")
    source_column_name: str = Field(..., alias="sourceColumnName")
    originating_facility: Optional[List[BaseType]] = Field(None, alias="originatingFacility")
    originating_site: List[BaseType] = Field(..., alias="originatingSite")


class Meta(BaseType):
    """Metadata for the response"""
    publisher: str
    license: str 
    license_name: str = Field(..., alias="licenseName")
    comment: str
    version: str
    has_format: List[str] = Field(..., alias="hasFormat")
    limit: int


class TimeseriesDatasetResponse(BaseModel):
    """Main response model for metadata dataset API"""
    meta: Meta
    items: List[TimeSeriesDataset]

    class Config:
        allow_population_by_field_name = True
        
    def get_datasets_by_site(self, site_id: str) -> List[TimeSeriesDataset]:
        """Get all datasets for a specific site"""
        return [
            dataset for dataset in self.items
            if any(site.id == site_id for site in dataset.originating_site)
        ]
    
    def get_datasets_by_variable(self, variable_id: str) -> List[TimeSeriesDataset]:
        """Get all datasets for a specific variable"""
        return [
            dataset for dataset in self.items
            if any(ts_type.measure.variable.id == variable_id for ts_type in dataset.type)
        ]
    
    def get_unique_variables(self) -> List[str]:
        """Get list of unique variable IDs"""
        variables = set()
        for dataset in self.items:
            for ts_type in dataset.type:
                variables.add(ts_type.measure.variable.id)
        return list(variables)


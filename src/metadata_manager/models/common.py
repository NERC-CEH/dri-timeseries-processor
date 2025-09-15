from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union


class ComponentType(Enum):
    CORRECTION = "correction"
    INFILLING = "infilling"
    QUALITY_CONTROL = "quality_control"
    DERIVATION = "calculate"
    AGGREGATION = "aggregate"


SERVICE_BASE_URI = "http://fdri.ceh.ac.uk"


def build_site_query_parameter(sites: List[str], network: str) -> List[Tuple]:
    """Build the site query parameters for the dataset endpoint.

    As we use the same key for multiple sites, it needs to be a list of tuples.

    Args:
        sites: A list of the sites to query.
        network: The network to query.

    Returns:
        A list of tuples with query parameter string and site.
    """
    return [("originatingSite", f"{SERVICE_BASE_URI}/id/site/{network}-{site.lower()}") for site in sites]


def build_column_query_parameter(columns: List[str]) -> List[Tuple]:
    """Build the column name query parameters for the dataset endpoint.

    As we use the same key for multiple columns, it needs to be a list of tuples.

    Args:
        columns: The column names to query.

    Returns:
        A list of tuples with query parameter string and column name.
    """
    return [("sourceColumnName", column) for column in columns]


def build_periodicity_query_parameter(periodicities: List[str]) -> List[Tuple]:
    """Build the periodicity query parameters for the dataset endpoint.

    As we use the same key for multiple periods, it needs to be a list of tuples.

    Args:
        periodicities: A list of the periodicities to query.

    Returns:
        A list of tuples with query parameter string and period.
    """
    return [("type.measure.aggregation.periodicity", period) for period in periodicities]


def build_timeseries_id_query_parameter(ts_ids: List[str]) -> List[Tuple]:
    """Build the timeseries id query parameters for the dataset endpoint.

    As we use the same key for multiple timeseries id, it needs to be a list of tuples.

    Args:
        ts_ids: A list of the timeseries IDs to query.

    Returns:
        A list of tuples with query parameter string and the timeseries ID.
    """
    return [("@id", ts_id) for ts_id in ts_ids]


def build_processing_config_timeseries_id_query_parameter(ts_ids: Union[List[str], str]) -> List[Tuple]:
    """Build the timeseries id query parameters for the processing config endpoint.

    As we use the same key for multiple timeseries id, it needs to be a list of tuples.

    Args:
        ts_ids: A list of the timeseries IDs to query.

    Returns:
        A list of tuples with query parameter string and the timeseries ID.
    """
    if isinstance(ts_ids, str):
        ts_ids = [ts_ids]
    return [("appliesToTimeSeries", ts_id) for ts_id in ts_ids]


def build_processing_config_type_query_parameter(config_type: str) -> List[Tuple]:
    """Build the type query parameter for the processing config endpoint.

    Args:
        config_type: The configuration type

    Returns:
        A list of tuples with query parameter string and the configuration type
    """
    return [("type", f"{SERVICE_BASE_URI}/ref/common/configuration-type/{config_type}")]


def build_processing_query_parameter(level: str) -> List[Tuple]:
    """Build the processing level query parameter for the dataset endpoint.

    As we use the same key for multiple processing levels, it needs to be a list of tuples.

    Args:
        level: The processing level

    Returns:
        A list of tuples with query parameter string and the processing level.
    """
    return [("type.processingLevel", f"{SERVICE_BASE_URI}/ref/common/processing-level/{level}")]


def build_view_query_parameter(view: str) -> List[Tuple]:
    """Build the view query parameter for the dataset endpoint.

    As we use the same key for multiple processing levels, it needs to be a list of tuples.

    Args:
        view: The response view

    Returns:
        A list of tuples with query parameter string and the view.
    """
    return [("_view", f"{view}")]


def get_interval_dates(interval: Optional[Dict[str, Union[str, datetime]]]) -> Tuple[datetime, Optional[datetime]]:
    """Extract and validate start and end dates from an interval dictionary.

    If the interval is None, a default start date of 1800 is used. The function validates that when an
    end date is provided, it occurs after the start date.

    Args:
        interval: A dictionary containing at minimum a 'startDate' key with a datetime value,
                and optionally an 'endDate' key with a datetime value. If None, a default
                start date is used.

    Returns:
        A tuple containing:
        - start_date: The start date of the interval
        - end_date: The end date of the interval, or None if not provided

    Raises:
        ValueError: If the end date is provided and is not after the start date.
    """
    end_date = None
    default_start_date = datetime(1800, 1, 1)

    if interval:
        start_date = datetime.fromisoformat(interval["startDate"]) if "startDate" in interval else default_start_date
        if "endDate" in interval:
            end_date = datetime.fromisoformat(interval["endDate"])
    else:
        # A missing interval means that it applies to the entire temporal range of the time series,
        # so set the start date to some nominal time before the project started.
        start_date = default_start_date

    if end_date:
        if end_date <= start_date:
            raise ValueError(f"end_date [{end_date}] must be after start_date [{start_date}]")

    return start_date, end_date

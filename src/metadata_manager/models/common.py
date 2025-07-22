from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union


class ComponentType(Enum):
    CORRECTION = "correction"
    INFILLING = "infilling"
    QUALITY_CONTROL = "quality_control"


# To get the last bit of a uri string, after the last trailing slash.
#   Allows for alpha characters, underscore and hyphen.
#   e.g. http://fdri.ceh.ac.uk/ref/cosmos/time-series/lwin_raw => lwin_raw
URI_ID_EXTRACT_REGEX = r".+\/([a-zA-Z0-9\-\_]+)$"

# To get the last bit of the site ID.
#   e.g. http://fdri.ceh.ac.uk/id/site/cosmos-chimn => chimn
SITE_ID_EXTRACT_REGEX = r".+\/\w+\-([a-zA-Z0-9]+)$"


def check_single_list_item(data: List) -> Any:
    """Checks that list has a single item within in.
    Args:
        data: List to check
    Returns:
        The first item of the list
    """
    if isinstance(data, list):
        num_items = len(data)
        if num_items != 1:
            raise ValueError(f"Single list check failed. {num_items} items found: {data}")
        data = data[0]
    return data


def get_property(key: str, prop: Dict[str, Any] | None) -> Any:
    """
    Given a dict like {key: [a,b,c]}, the first value of the list will be returned
    Given a dict like {key: a}, a will be returned

    Args:
        key: the key to look for
        prop: the dict to search in.

    Returns:
        The value associated with the key.
    """
    if not prop:
        return None

    values = prop.get(key)
    if isinstance(values, list):
        return values[0]

    return values


def build_site_query_parameter(sites: List[str]) -> List[Tuple | None]:
    """Build the site query parameters for the dataset endpoint.

    As we use the same key for multiple sites, it needs to be a list of tuples.

    Args:
        sites: A list of the sites to query.

    Returns:
        A list of tuples with query parameter string and site.
    """
    return [("originatingSite", f"http://fdri.ceh.ac.uk/id/site/cosmos-{site.lower()}") for site in sites]


def build_column_query_parameter(columns: List[str]) -> List[Tuple | None]:
    """Build the column name query parameters for the dataset endpoint.

    As we use the same key for multiple columns, it needs to be a list of tuples.

    Args:
        columns: The column names to query.

    Returns:
        A list of tuples with query parameter string and column name.
    """
    return [("sourceColumnName", column) for column in columns]


def build_periodicity_query_parameter(periodicities: List[str]) -> List[Tuple | None]:
    """Build the periodicity query parameters for the dataset endpoint.

    As we use the same key for multiple periods, it needs to be a list of tuples.

    Args:
        periodicities: A list of the periodicities to query.

    Returns:
        A list of tuples with query parameter string and period.
    """
    return [("type.measure.aggregation.periodicity", period) for period in periodicities]


def build_timeseries_def_query_parameter(ts_defs: List[str]) -> List[Tuple | None]:
    """Build the timeseries definition query parameters for the dataset endpoint.

    As we use the same key for multiple timeseries defs, it needs to be a list of tuples.

    Args:
        ts_defs: A list of the timeseries definitions to query.

    Returns:
        A list of tuples with query parameter string and the timeseries definition.
    """
    return [("type", ts_def) for ts_def in ts_defs]


def build_timeseries_id_query_parameter(ts_ids: List[str]) -> List[Tuple | None]:
    """Build the timeseries id query parameters for the dataset endpoint.

    As we use the same key for multiple timeseries id, it needs to be a list of tuples.

    Args:
        ts_defs: A list of the timeseries definitions to query.

    Returns:
        A list of tuples with query parameter string and the timeseries definition.
    """
    return [("id", ts_id) for ts_id in ts_ids]


def build_processing_query_parameter(level: str) -> List[Tuple | None]:
    """Build the processing level query parameter for the dataset endpoint.

    As we use the same key for multiple processing levels, it needs to be a list of tuples.

    Args:
        level: The processing level

    Returns:
        A list of tuples with query parameter string and the processing level.
    """
    return [("type.processingLevel", f"http://fdri.ceh.ac.uk/ref/common/processing-level/{level}")]


def build_view_query_parameter(view: str) -> List[Tuple | None]:
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

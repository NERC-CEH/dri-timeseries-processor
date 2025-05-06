import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import isodate
import polars as pl
from polars.dataframe.group_by import GroupBy

logger = logging.getLogger(__name__)


def validate_iso8601_duration(duration: str) -> bool:
    """Validate if the given string is a valid ISO 8601 duration.

    Args:
        duration: The duration string to validate.

    Returns:
        True if the duration is valid, False otherwise.
    """
    try:
        isodate.parse_duration(duration)
        return True
    except isodate.ISO8601Error:
        return False


def remove_protocol_from_url(url: str) -> str:
    """Remove the protocol from a URL.

    Args:
        url: URL to remove protocol from

    Returns:
        URL with protocol removed

    Examples:
        >>> remove_protocol_from_url("https://www.example.com")
        "www.example.com"
    """
    endpoint_url = urlparse(url)
    # Remove the protocol scheme by setting it to an empty string
    endpoint_url = "".join(endpoint_url[1:])
    return endpoint_url


def steralize_dates(
    start_date: Union[date, datetime], end_date: Optional[Union[date, datetime]] = None
) -> Tuple[Union[date, datetime], datetime]:
    """
    Configures and validates start and end dates.

    Args:
        start_date: The start date.
        end_date: The end date. If None, defaults to start_date.

    Returns:
        A tuple containing the start date and the end date.

    Raises:
        UserWarning: If the start date is after the end date.
    """
    # If end_date is not provided, set it to start_date
    if end_date is None:
        end_date = start_date

    # Ensure the start_date is not after the end_date
    if start_date > end_date:
        raise UserWarning(f"Start date must come before end date: {start_date} > {end_date}")

    # If start_date is of type date, convert it to datetime with time at start of the day
    if isinstance(start_date, date) and not isinstance(start_date, datetime):
        start_date = datetime.combine(start_date, datetime.min.time())

    # If end_date is of type date, convert it to datetime to include the entire day
    if isinstance(end_date, date) and not isinstance(end_date, datetime):
        end_date = datetime.combine(end_date, datetime.max.time())

    return start_date, end_date


def group_by_date_site_id(df: pl.DataFrame) -> List[GroupBy]:
    """Group a dataframe by the date and site_id column.

    Args:
        df: A polars dataframe

    Returns:
        A list of dataframes grouped by date and site_id.
    """

    return [
        (group[0][0], group[0][1], group[1]) for group in df.group_by([pl.col("time").dt.date(), pl.col("SITE_ID")])
    ]


def missing_expr(column_name: str) -> pl.Expr:
    """Return expression for missing values in column.

    Args:
        column_name: Data column name

    Returns:
        Expression for missing values
    """
    return pl.col(column_name).is_null() | pl.col(column_name).is_nan()


def not_missing_expr(column_name: str) -> pl.Expr:
    """Return expression for not missing values in column.

    Args:
        column_name: Data column name

    Returns:
        Expression for not missing values
    """
    return pl.col(column_name).is_not_null() & pl.col(column_name).is_not_nan()


def remove_sites_not_in_store(sites: list, metadata_sites: list) -> list:
    """Filter out sites that are not in the metadata store.

    Args:
        sites: Requested sites
        metadata_sites: Sites in the metadata store

    Returns:
        sites in both parameters.
    """

    matching_sites = list(set(sites) & set(metadata_sites))
    missing_sites = list(set(sites) - set(metadata_sites))

    if missing_sites:
        raise ValueError(
            f"The following sites {missing_sites} are not in the metadata store. Remove from '--sites' argument."
        )

    return matching_sites


def split_data_for_processing(df: pl.DataFrame, metadata: Dict[str, Any] = None) -> List[GroupBy]:
    """Split the data ready for processing.

    Data split by site_id with metadata added.

    Args:
        df: A polars dataframe
        metadata: Metadata to be attached to each dataframe to be processed

    Returns:
        A list of dataframes grouped by site_id with metadata
    """
    # Structure of return and the way we attach metadata will change when we introduce the
    # ability to have multiple resolutions

    return [(site[0], data, metadata) for site, data in df.group_by([pl.col("SITE_ID")])]


def extract_unique_timeseries_defs(timeseries_ids_metadata: Dict[str, Dict[str, str]]) -> List[str]:
    """Extract a unique list of timeseries definitions from the timeseries ids to be processed.

    Args:
        timeseries_ids_metadata: metadata about the timeseries ids to process

    Returns:
        A list of unique timeseries definitions
    """
    unique_timeseries_defs = {value["ts_def"] for value in timeseries_ids_metadata.values()}

    return list(unique_timeseries_defs)


def extract_dependent_timeseries_defs(
    timeseries_defs_derivation_map: Dict[str, Dict[str, Union[str, List[str | None]]]],
) -> List[str]:
    """Extract a list of dependent timeseries definitions.

    Args:
        timeseries_defs_derivation_map: An object with all the dependencies

    Returns:
        A list of all dependent timeseries definitions.
    """

    return list({items for items in timeseries_defs_derivation_map.values() for items in items["inputs"]})


def group_timeseries_to_process(
    timeseries_ids_metadata: Dict[str, Dict[str, str]],
    timeseries_defs_derivation_map: Dict[str, Dict[str, Union[str, List[str | None]]]],
) -> Dict[str, Union[str, List[str]]]:
    """Return timeseries ids that are to be processed.
    This function will group the timeseries ids by their site, resolution and periodicity.

    Args:
        timeseries_ids_metadata: metadata about the timeseries ids to process
        timeseries_defs_derivation_map: An object with all the dependencies

    Returns:
        A dictionary of timeseries ids for each set of site_id, resolution and periodicity.
    """
    grouped_timeseries = {}

    for timeseries_id, metadata in timeseries_ids_metadata.items():
        # Only add the timeseries ids with no derivation method.
        # These are the TS that are to be processed.
        process_method = timeseries_defs_derivation_map[metadata["ts_def"]].get("method_type")
        if process_method is None:
            site_id = metadata["sourceSite"]
            resolution = metadata["resolution"]
            periodicity = metadata["periodicity"]

            # Create a unique key for the group based on site_id, resolution and periodicity
            group_key = f"{site_id}_{resolution}_{periodicity}"

            # Add the timeseries id to the group
            if group_key not in grouped_timeseries:
                grouped_timeseries[group_key] = {
                    "site_id": site_id,
                    "resolution": resolution,
                    "periodicity": periodicity,
                    "timeseries_ids": [],
                }

            grouped_timeseries[group_key]["timeseries_ids"].append(timeseries_id)

    return grouped_timeseries

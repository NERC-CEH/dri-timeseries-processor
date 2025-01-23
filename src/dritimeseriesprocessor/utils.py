import logging
from datetime import date, datetime
from typing import List, Optional, Tuple, Union
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


def steralize_site_ids(site_ids: Optional[List[str]] = None) -> List[str]:
    """
    Configures site IDs into a list format.

    Args:
        site_ids: A single site ID as a string or a list of site IDs.
            If None, defaults to an empty list.

    Returns:
        A list of site IDs.
    """
    # TODO
    if site_ids is None or site_ids == "":
        # If no site IDs are provided, return an empty list
        site_ids = []
    elif isinstance(site_ids, str):
        # If a single site ID string is provided, convert it to a list
        site_ids = [site_ids]

    return site_ids


def group_by_date_site_id(df: pl.DataFrame) -> List[GroupBy]:
    """Group a dataframe by the date and site_id column."""

    return [
        (group[0][0], group[0][1], group[1]) for group in df.group_by([pl.col("time").dt.date(), pl.col("SITE_ID")])
    ]


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

    for site in missing_sites:
        logger.info(f"Requested {site} does not exist in the metadata store. Removing from query.")

    return matching_sites

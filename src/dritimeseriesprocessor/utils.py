import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import isodate
import polars as pl
from polars.dataframe.group_by import GroupBy

from dritimeseriesprocessor.typing import DerivationMetadata, TimeseriesContainer, TimeseriesContainerWithDerivations

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


def group_by_date(df: pl.DataFrame) -> List[GroupBy]:
    """Group a dataframe by the date.

    Args:
        df: A polars dataframe

    Returns:
        dataframes grouped by date.
    """

    return [(group[0][0], group[1]) for group in df.group_by([pl.col("time").dt.date()])]


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


def map_def_to_id(ts_def: str, site_id: str, ts_ids: Dict[str, TimeseriesContainer]) -> Dict[str, str]:
    """Map timeseries definition to its corresponding timeseries id given the site id.

    Args:
        ts_def: A timeseries definition
        site_id: The site id to filter the timeseries ids by
        ts_ids: Metadata for timeseries ids

    Returns:
        A timeseries id.
    """
    # Find the TS ID that matches the input definition and sourceSite
    for check_ts_id, check_metadata in ts_ids.items():
        if check_metadata.get("ts_def") == ts_def and check_metadata.get("sourceSite") == site_id:
            return check_ts_id
    raise ValueError(f"Could not find TS ID for TS definition {ts_def} and sourceSite {site_id}")


def merge_ts_def_metadata(
    ts_ids: Dict[str, TimeseriesContainer],
    timeseries_defs_derivation_map: Dict[str, DerivationMetadata],
) -> Dict[str, TimeseriesContainerWithDerivations]:
    """Merge timeseries definitions metadata into the timeseries ids metadata and add whether to load the data.

    Args:
        ts_ids: Metadata for timeseries ids to process
        timeseries_defs_derivation_map: A map of timeseries definitions and their metadata

    Returns:
        A dictionary with the merged metadata.
    """
    for ts_id, ts_metadata in ts_ids.items():
        ts_def = ts_metadata["ts_def"]

        if ts_def in timeseries_defs_derivation_map:
            # Add the method and method type
            method_type = timeseries_defs_derivation_map[ts_def].get("method_type")
            method = timeseries_defs_derivation_map[ts_def].get("method")

            # timeseries_defs_derivation_map contains the dependency TS definitions (inputs). Here we want the
            # specific dependancy TS IDs (instead of defs). Map the defs to their corresponding TS IDs.
            site_id = ts_metadata["sourceSite"]
            inputs = [
                map_def_to_id(input_def, site_id, ts_ids)
                for input_def in timeseries_defs_derivation_map[ts_def]["inputs"]
            ]

        else:
            raise ValueError(f"Timeseries definition {ts_def} not found in derivation map for {ts_id}")

        # Raw timeseries ids with no derivation method is data that must be loaded.
        load = True if ts_metadata["processing_level"] == "raw" and method_type is None else False

        ts_def_dict = {"method_type": method_type, "method": method, "inputs": inputs, "load": load}

        ts_metadata.update(ts_def_dict)

    return ts_ids

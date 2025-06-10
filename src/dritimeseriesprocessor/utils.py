import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import isodate
import polars as pl
from polars.dataframe.group_by import GroupBy

from time_stream import TimeSeries

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


class TimeSeriesGroupMetadata(object):
    """Class to hold the metadata timeseries IDs that will be grouped together into a TimseSeries object"""
    def __init__(self, id: str, site_id: str, resolution: str, periodicity: str, process_level: str,
                 timeseries_ids_metadata: Dict[str, Dict[str, str]]={}):
        """
        Args:
            id: The id of the group
            site_id: The site ID for the timeseries group.
            resolution: The resolution of the timeseries
            periodicity: The periodicity of the timeseries
            process_level: The processing level of the timeseries
            timeseries_ids_metadata: Metadata for the timeseries IDs in the group
        """
        self.id = id
        self.site_id = site_id
        self.resolution = resolution
        self.periodicity = periodicity
        self.process_level = process_level
        self.timeseries_ids_metadata = timeseries_ids_metadata

    def column_metadata(self, keys=None) -> Dict[str, Dict[str, str]]:
        """Return the metadata for the timeseries IDs in the group, keyed by column name.
        This method is used to return a column metadata dictionary compatible with the
        TimeSeries constructor.

        Args:
            keys: Optional list of keys to filter the metadata by. If None, all metadata is returned.

        Returns:
            A dictionary of column names and their metadata.
        """
        if keys is None:
            keys = self.timeseries_ids_metadata.keys()

        col_metadata = {}
        for ts_id, metadata in self.timeseries_ids_metadata.items():
            col_name = metadata["sourceColumnName"]
            if col_name in col_metadata:
                raise ValueError(f"Duplicate column name found: {col_name}")

            col_metadata[col_name] = {}
            if "ts_id" in keys:
                col_metadata[col_name] = {"ts_id": ts_id}

            for key in keys:
                if key not in ("ts_id", "sourceColumnName"):
                    if key in metadata:
                        col_metadata[col_name][key] = metadata[key]
                    else:
                        logger.warning(f"Key {key} not found in metadata for timeseries ID {ts_id}")

        return col_metadata


def group_timeseries(
    timeseries_ids_metadata: Dict[str, Dict[str, str]],
) -> Dict[str, TimeSeriesGroupMetadata]:
    """Group the timeseries ids by site, resolution, periodicity and process level, i.e. IDs that will be contained
    in the same TimeSeries object. Create a unique key for each group and add it to the metadata.

    Args:
        timeseries_ids_metadata: metadata about the timeseries ids to process

    Returns:
        A dictionary of timeseries ids for each set of site_id, resolution and periodicity.
    """
    timeseries_groups = {}

    for timeseries_id, metadata in timeseries_ids_metadata.items():
        site_id = metadata["sourceSite"]
        resolution = metadata["resolution"]
        periodicity = metadata["periodicity"]
        process_level = metadata["processing_level"]

        # Create a unique key for the group based on site_id, resolution and periodicity
        group_id = f"{site_id}_{resolution}_{periodicity}_{process_level}"

        # Add this key to the metadata
        metadata["ts_group_id"] = group_id

        if group_id not in timeseries_groups:
            timeseries_groups[group_id] = TimeSeriesGroupMetadata(
                id = group_id,
                site_id = site_id,
                resolution = resolution,
                periodicity = periodicity,
                process_level = process_level,
                timeseries_ids_metadata = {}
            )

        # Add the timeseries id metadata to the group
        timeseries_groups[group_id].timeseries_ids_metadata[timeseries_id] = metadata

    return timeseries_groups

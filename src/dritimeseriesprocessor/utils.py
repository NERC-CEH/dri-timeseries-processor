import asyncio
import functools
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import isodate
import polars as pl
from polars.dataframe.group_by import GroupBy

from dritimeseriesprocessor.local_typing import TimeseriesContainer
from metadata_manager.models.common import SERVICE_BASE_URI
from metadata_manager.models.schemas.data_processing_configurations import ConfigItem

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


def sterilize_dates(
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
    if type(start_date) is date:
        start_date = datetime.combine(start_date, time.min)

    # If end_date is of type date, convert it to datetime to include the entire day
    if type(end_date) is date:
        end_date = datetime.combine(end_date, time.max)

    return start_date, end_date


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


def extract_dep_ts(config: ConfigItem, ts_ids: Dict[str, TimeseriesContainer]) -> ConfigItem:
    """Configs can contain dependency time series IDs. These should be replaced with the actual data

    Args:
        config: A correction configuration object
        ts_ids: Metadata and data for timeseries ids

    Returns:
        The updated correction configuration object with dependency time series mapped to ts.TimeFrame objects.
    """
    # Map dependency time series IDs to ts.TimeFrame objects
    if "dep_ts" in config.parameters:
        if isinstance(config.parameters["dep_ts"], str):
            dep_ts_ids = [config.parameters["dep_ts"]]
        else:
            dep_ts_ids = config.parameters["dep_ts"]

        for dep_ts_id in dep_ts_ids:
            full_dep_ts_id = f"{SERVICE_BASE_URI}/id/dataset/{dep_ts_id.lower()}"
            if full_dep_ts_id not in ts_ids:
                raise ValueError(f"Dependency time series ID {dep_ts_id} not found in provided data.")

            dep_ts = ts_ids[full_dep_ts_id]["data"]
            # Add the dependency time series to the parameters
            config.parameters[dep_ts.metadata["column_name"].lower()] = dep_ts

        # No longer need this key in the parameters once we've got the dependency time series
        config.parameters.pop("dep_ts")

    return config


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


def map_def_to_id(ts_def: str, site_id: str, ts_ids: Dict[str, TimeseriesContainer]) -> str:
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


def call_method_async(method: Callable, arg_list: List[Any]) -> List[Any]:
    """
    Execute a single method asynchronously with multiple sets of arguments.

    This function uses a ThreadPoolExecutor to run the given method concurrently
    with different sets of arguments.

    Args:
        method (callable): The method to be executed asynchronously.
        arg_list (list): A list of argument tuples. Each tuple contains the arguments
                         for one call to the method.

    Returns:
        list: A list of results from the executed method calls.

    Example:
        results = call_method_async(my_method, [(1, 'a'), (2, 'b'), (3, 'c')])
    """

    async def run_in_executor(
        executor: ThreadPoolExecutor, method: Callable, loop: asyncio.AbstractEventLoop, args: Any
    ) -> asyncio.Future:
        """
        Run a method in the provided executor with the given arguments.

        Args:
            executor: The executor to run the method in.
            method: The method to be executed.
            loop: Event loop
            args: Arguments to be passed to the method.

        Returns:
            The result of the method execution.
        """
        if not hasattr(args, "__iter__"):
            args = [args]

        return await loop.run_in_executor(executor, functools.partial(method, *args))

    async def main(loop: asyncio.AbstractEventLoop) -> List[Any]:
        """
        Main coroutine that sets up and runs all tasks.

        Returns:
            list: Results from all executed method calls.
        """
        with ThreadPoolExecutor() as executor:
            tasks = [run_in_executor(executor, method, loop, args) for args in arg_list]
            return await asyncio.gather(*tasks)

    loop = asyncio.new_event_loop()
    return loop.run_until_complete(main(loop))

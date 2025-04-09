"""Handle the command line arguments."""

import argparse
import datetime
from argparse import ArgumentParser
from datetime import date, timedelta
from typing import Tuple

import isodate
from isodate import Duration

from dritimeseriesprocessor.utils import remove_sites_not_in_store


def parse_args(args: list) -> ArgumentParser:
    """Build a parser instance and get the arguments.

    period: required
    sites: optional (default is all sites)
    end_date: optional (default is todays date).

    Returns:
        An instance of ArguementParser.
    """
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        "period",
        help=(
            """A valid ISO8601 period to extract level 0 data for. Should be a combination of
            days, weeks, months or years:\nP1D: previous day\nP1Y: previous year\nPT6H: invalid as using hours"""
        ),
    )
    parser.add_argument(
        "--sites",
        help=(
            """The sites to extract. Must be a string of sites (upper or lower case) seperated by a comma
            e.g. ALIC1,BUNNY or alic1,bunny. If not provided all sites will be extracted."""
        ),
    )
    parser.add_argument(
        "--vars",
        help=(
            """The col_names to extract. Must be a string of col_names by column name (upper or lower case) seperated by
            a comma e.g. TA,RN or ta,rn. If not provided all col_names will be extracted."""
        ),
    )
    parser.add_argument(
        "-ed",
        "--end_date",
        help=("The date to start the data extraction from. Must be of the form YYYY-MM-DD (default: todays date)"),
        default=date.today().strftime("%Y-%m-%d"),
    )

    return parser.parse_args(args)


def build_date_range(period: str, end_date: str, environment: str) -> Tuple[str, str]:
    """Build the start and end date used in the duckdb query.

    Date must be in the format YYYY-MM-DD.
    If no end_date is entered, then the default is todays date.
    When running locally, the default end_date value is overwritten by
    '2024-03-10' to ensure local data is always pulled in.

    Args:
        period: The amount of time to extract data for e.g. the previous month
        end_date: The date to extract data upto
        environment: The environment the app is running in

    Returns:
        A tuple of the start and end date
    """

    # When running locally, we just need a date that has been loaded into the
    # `parquet-data` folder.
    if environment == "local":
        end_date = "2024-03-10"

    end_date = validate_end_date(end_date)

    # Validate the period
    period = validate_period(period, end_date)

    # Start date built from end_date and period
    start_date = end_date - period

    return start_date, end_date


def validate_period(period: str, end_date: date) -> timedelta:
    """Validate the period argument is an ISO8601 duration.

    The app only accepts durations from days upwards, and raises an
    error if a time component is provided.

    Args:
        period: The amount of time to extract data for e.g. the previous month

    Raises:
        ValueError: If the period has a time component or is an incorrect ISO8601 period.

    Returns:
        A timedelta object of the period.
    """
    if "T" in period:
        raise ValueError("Period should not have a time component")

    try:
        period = isodate.parse_duration(period)

        # if the period contains years, isodate converts to its own Duration class
        # as timedelta cannot take years. Using in-built methods we can then convert
        # Duration to a time delta instance made up of days.
        if isinstance(period, Duration):
            period = period.totimedelta(end=end_date)

        return period

    except ValueError:
        raise ValueError(
            """Incorrect period format. Should be a valid ISO8601 duration containing a combination of days,
            months or years e.g. P3Y6M4D or P3Y12W3D"""
        )


def validate_end_date(end_date: str) -> str:
    """Validate the end_date argument is an ISO8601 date.

    Args:
        end_date: The date to extract data upto

    Raises:
        ValueError: If the end date is an incorrect ISO8601 date.

    Returns:
        A datetime object of the end date
    """
    try:
        return datetime.date.fromisoformat(end_date)
    except ValueError:
        raise ValueError("Incorrect date format, should be YYYY-MM-DD")


def validate_sites(sites: str, metadata_sites: list) -> list:
    """Validate the sites entered.

    Checks user entered sites against the metadata site list and removes
    if not contained.

    Args:
        sites: The sites to process
        metadata_sites: The sites from the metadata store
    """
    if sites is not None:
        sites_list = sites.split(",")

        checked_sites = []
        # Rough check for formatting
        for site in sites_list:
            if not site.isalnum():
                raise ValueError(f"Site {site} should only contain letters and numbers.")
            else:
                checked_sites.append(site.upper())

        # Filter out user requested sites that are not in the metadata store
        sites = remove_sites_not_in_store(checked_sites, metadata_sites)
    else:
        sites = metadata_sites

    return sites


def validate_col_names(col_names: str) -> list:
    """Validate the col_names entered.

    Args:
        col_names: The col_names to process
        network: The project network the data comes from.
    """
    if col_names is not None:
        col_name_list = col_names.split(",")

        checked_col_names = []

        # Rough check for formatting
        for variable in col_name_list:
            if not variable.isalnum():
                raise ValueError(f"Variable {variable} should only contain letters and numbers.")
            else:
                checked_col_names.append(variable.upper())

        return checked_col_names
    else:
        return []

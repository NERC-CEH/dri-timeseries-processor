"""Handle the command line arguments."""

import argparse
import datetime
from argparse import ArgumentParser
from datetime import date, timedelta
from typing import Tuple

import isodate


def get_args() -> ArgumentParser:
    """Build a parser instance and get the arguments.

    Period is required; end_date is optional (default is todays date).

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
        "-ed",
        "--end_date",
        help=("The date to start the data extraction from. Must be of the form YYYY-MM-DD (default: todays date)"),
        default=date.today().strftime("%Y-%m-%d"),
    )

    return parser.parse_args()


def build_start_end_dates(period: str, end_date: str, environment: str) -> Tuple[str, str]:
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
    if environment == "local":
        end_date = "2024-03-10"

    end_date = validate_end_date(end_date)

    # Validate the period
    period = validate_period(period)

    # Start date built from end_date and period
    start_date = end_date - period

    return start_date, end_date


def validate_period(period: str) -> timedelta:
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
        return isodate.parse_duration(period)
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

"""Some descrition here"""
import argparse
import isodate
import datetime
from argparse import ArgumentParser
from datetime import date, timedelta

from typing import Tuple

def get_args() -> ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("period")
    parser.add_argument("-ed", "--end_date", action="store_true")
    
    return parser.parse_args()


def build_start_end_dates(period: str, end_date: str) -> Tuple[str, str]:
    # If no end_date then current day is taken.
    # Date must be in format YYYY-MM-DD (need to validate)
    if not end_date:
        end_date = date.today()
    else:
        end_date = validate_end_date(end_date)
    

    # Validate the period
    period = validate_period(period)

    # Start date built from end_date and period
    start_date = end_date - period

    return start_date, end_date


def validate_period(period: str) -> timedelta:
    # must be days, month, year
    if 'T' in period:
        raise ValueError("Period should not have a time component")
    
    try:
        period = isodate.parse_duration(period)
    except ValueError:
        raise ValueError("Incorrect period format. Should be a valid ISO8601 duration containing a combination of days, months or years e.g. P3Y6M4D or P3Y12W3D")
    
    return period

def validate_end_date(end_date: str) -> str:

    try:
        datetime.date.fromisoformat(end_date)
    except ValueError:
        raise ValueError("Incorrect date format, should be YYYY-MM-DD")

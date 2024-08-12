"""Module for validating the filter config json."""

import datetime
import json
import logging
import os

logger = logging.getLogger(__name__)


def validate(filter_config_path: str | os.PathLike) -> None:
    """Validates the filter config json.

    Args:
        filter_config: Path to filter_config.json

    Returns:
        Validated filter config json object.
    """
    # Load filter config
    with open(filter_config_path) as f:
        filter_config = json.load(f)

    for dataset in filter_config["datasets"]:
        # Dates
        start_date = dataset["range"][0]
        end_date = dataset["range"][1]

        validate_date(start_date)
        validate_date(end_date)

        if start_date > end_date:
            logger.error(f"Start date must come before end date: {start_date} > {end_date}")
            raise ValueError

        # Dataset type
        valid_types = ["PRECIP_1MIN_2024_LOOPED", "SOILMET_30MIN_2024_LOOPED"]

        if dataset["type"] not in valid_types:
            logger.error(f"Type must be one of {valid_types}")
            raise ValueError

        # Columns
        if "columns" in dataset and not isinstance(dataset["columns"], list):
            logger.error("Columns must be list type.")
            raise ValueError

    return filter_config


def validate_date(date_text: str) -> None:
    """Checks whether date string is valid ISO format.

    Args:
        date_text: The date to check as a string.

    Raises:
        ValueError: If the date is not the correct format.
    """
    try:
        datetime.date.fromisoformat(date_text)
    except ValueError:
        raise ValueError("{date_text}: Incorrect data format, should be YYYY-MM-DD")

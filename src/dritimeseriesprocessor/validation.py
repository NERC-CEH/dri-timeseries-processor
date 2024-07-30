"""Module for validating the filter config json."""

import datetime
import logging

logger = logging.getLogger(__name__)

def validate_filter_config(filter_config):

    for dataset in filter_config['datasets']:

        # Dates
        start_date = dataset['range'][0]
        end_date = dataset['range'][1]

        validate_date(start_date)
        validate_date(end_date)

        if start_date > end_date:
            logger.error(f"Start date must come before end date: {start_date} > {end_date}")
            raise ValueError
        
        # Dataset type
        valid_types = ['LEVEL_-1_PRECIP_1MIN_2024_LOOPED',
                       'LEVEL_-1_SOILMET_1MIN_2024_LOOPED' ]

        if dataset['type'] not in valid_types:
            logger.error(f"Type must be one of {valid_types}")
            raise ValueError

    # Columns
    if 'columns' in filter_config and not isinstance(filter_config['columns'], list):
        logger.error(f"Columns must be list type.")
        raise ValueError


def validate_date(date_text):
    try:
        datetime.date.fromisoformat(date_text)
    except ValueError:
        raise ValueError("Incorrect data format, should be YYYY-MM-DD")
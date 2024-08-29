"""Module for formatting log messages"""

import logging
import traceback
from datetime import datetime
from typing import Tuple, Type


class LogFormatter(logging.Formatter):
    """
    A custom log formatter that provides a structured log format.

    This formatter creates log entries with a timestamp, log level, logger name,
    and either the log message or exception traceback.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the specified log record as text.

        Args:
            record: A LogRecord instance representing the event being logged.

        Returns:
            str: A formatted string containing the log entry details.
        """
        timestamp = self.formatTime(record)
        level = record.levelname
        logger_name = record.name

        log_entry = f"{timestamp} - {level} - {logger_name} - "

        if record.exc_info:
            tb = self.formatException(record.exc_info)
            # Replace newlines in traceback with pipe symbols
            tb = " | ".join(line.strip() for line in tb.split("\n") if line.strip())
            log_entry += f" | Exception: {tb}"
        else:
            log_entry += record.getMessage()

        return log_entry

    def formatTime(self, record: logging.LogRecord) -> datetime:
        """
        Format the creation time of the specified LogRecord.

        Args:
            record: A LogRecord instance representing the event being logged.

        Returns:
            datetime: A datetime object representing the record's creation time.
        """
        return datetime.fromtimestamp(record.created)

    def formatException(self, exc_info: Tuple[Type[BaseException], BaseException]) -> str:
        """
        Format the specified exception information as a string.

        Args:
            exc_info: A tuple containing exception information.

        Returns:
            str: A string representation of the exception traceback.
        """
        return "".join(traceback.format_exception(*exc_info)).strip()


def setup_logging(level: int = logging.INFO) -> None:
    """
    Set up basic logging configuration with a custom formatter.

    This function configures the root logger with a StreamHandler and
    the custom LogFormatter. It removes any existing handlers before
    adding the new one.

    Args:
        level: The logging level to set for the root logger. Defaults to logging.INFO.

    Returns:
        None
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    handler = logging.StreamHandler()
    formatter = LogFormatter()
    handler.setFormatter(formatter)

    root_logger.handlers = [handler]

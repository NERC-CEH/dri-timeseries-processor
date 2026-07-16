import inspect
import logging
import os
import sys

from driutils.json_logger import json_formatter, log_extras  # noqa: F401
from loguru import logger


class _InterceptHandler(logging.Handler):
    """Bridges stdlib logging to loguru.

    All application modules use Python's stdlib logging (`logging.getLogger(__name__)`).
    This handler intercepts those records and forwards them to loguru so they get the
    same JSON/human-readable formatting as everything else, without needing to rewrite
    every module to import loguru directly.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Forward a stdlib log record to loguru, preserving the original call site.

        Args:
            record: the stdlib log record to forward.
        """
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk up from this frame, past the stdlib logging internals, to the real call site.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _local_formatter(record: dict) -> str:
    """Human-readable log format for local development.

    The standard JSON format is machine-readable but hard to follow locally,
    so this formatter is used when `environment` is not set.

    Args:
        record: the loguru record object.

    Returns:
        A log string
    """
    timestamp = record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    parts = [
        f"time={timestamp}",
        f"level={record['level'].name}",
        f"thread={record['thread'].id}",
        f"loc={record['name']}:{record['line']}",
    ]

    for key, value in record["extra"].items():
        parts.append(f"{key}={value}")
    parts.append(f"message={record['message']}")

    return (" ".join(parts) + "\n").replace("{", "{{").replace("}", "}}")


def setup_logger(service_name: str) -> None:
    """Configure loguru for the service based on the run environment.

    Uses human-readable logs locally and structured JSON in staging/production.
    Also intercepts the root stdlib logger so existing `logging.getLogger(__name__)`
    call sites throughout the codebase are routed through loguru unchanged.

    Args:
        service_name: the name of the service
    """
    is_local = "environment" not in os.environ

    def _json_formatter(record: dict) -> str:
        return json_formatter(record, service_name=service_name)

    formatter = _local_formatter if is_local else _json_formatter

    logger.remove()
    logger.add(sys.stdout, format=formatter, colorize=False, backtrace=False)  # type: ignore[arg-type]

    logging.basicConfig(handlers=[_InterceptHandler()], level=logging.INFO, force=True)

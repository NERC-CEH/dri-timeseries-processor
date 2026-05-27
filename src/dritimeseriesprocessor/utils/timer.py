"""
Timing utilities for logging duration of code blocks and functions.

This module provides:
- ``ElapsedTimer``: a context manager for timing blocks of code
- ``log_duration``: a decorator built on top of ``ElapsedTimer`` for timing entire function executions
"""

import logging
import time
from dataclasses import dataclass
from functools import wraps
from types import TracebackType
from typing import Any, Callable, Self, Type, TypeVar

logger = logging.getLogger(__name__)


@dataclass
class ElapsedTimer:
    """Context manager for logging execution time of a block of code.

    Measures the elapsed time between entering and exiting a ``with`` block and write a log message on exit.
    The elapsed duration is also stored on the instance and may be accessed after the context exits.

    Args:
        message: Message prefix to include in the log output.
        level: Logging level at which to emit the timing message.
        header: If True, emit a separator line *before* the timing message.
        footer: If True, emit a separator line *after* the timing message.
        separator: String used for header/footer separators.

    Attributes:
        elapsed: Elapsed time in seconds, populated after context exit.

     Example:
         >>> with ElapsedTimer("Total processing time:", header=True) as t:
         ...     # do something
    """

    message: str
    level: int = logging.INFO
    header: bool = False
    footer: bool = False
    separator: str = "-" * 30

    elapsed: float | None = None

    def __enter__(self) -> Self:
        """Start timing on context entry."""
        self._start = time.perf_counter()
        return self

    def __exit__(
        self, exc_type: Type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> bool:
        """Stop timing and write log

        Args:
            exc_type: Exception type, if raised.
            exc: Exception instance, if raised.
            tb: Traceback, if raised.
        """
        self.elapsed = time.perf_counter() - self._start
        if self.header:
            logger.log(self.level, self.separator)

        logger.log(self.level, "%s: %.2f seconds", self.message, self.elapsed)

        if self.footer:
            logger.log(self.level, self.separator)
        return False


F = TypeVar("F", bound=Callable[..., Any])


def log_duration(
    message: str,
    level: int = logging.INFO,
    header: bool = False,
    footer: bool = False,
    separator: str = "-" * 30,
) -> Callable[[F], F]:
    """Decorator for logging the execution duration of a function. Wraps the decorated function in an ``ElapsedTimer``
    context manager, writing the log message when the function finishes.

    Args:
        message: Message prefix to include in the log output.
        level: Logging level at which to write the message.
        header: If True, write a separator line before the message.
        footer: If True, write a separator line after the message.
        separator: String used for header/footer separators.

    Returns:
        The decorator for timing the function.

    Example:
        >>> @log_duration("Total processing time:", header=True)
        ... def run_pipeline():
        ...     process()
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            with ElapsedTimer(
                message=message,
                level=level,
                header=header,
                footer=footer,
                separator=separator,
            ):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator

"""Shared method contract for all operation families (correction, QC, infill, aggregation, derivation).

Every registered method - regardless of family - implements `run(tf, config) -> result`. The two type
parameters let each family fix its own input and result type: most families transform a `TimeFrame` into
another `TimeFrame`; QC checks a `TimeFrame` and returns a boolean `pl.Series` mask; derivation is generative
so its input is `TimeFrame | None`.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar, Generic, TypeVar

from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import ConfigurationType

InputT = TypeVar("InputT")
ResultT = TypeVar("ResultT")


class OperationMethod(Operation, ABC, Generic[InputT, ResultT]):
    """Base class for a single operation method: run(tf, config) -> result."""

    operation_type: ClassVar[ConfigurationType]

    @abstractmethod
    def run(self, tf: InputT, config: DataProcessingMethodConfig) -> ResultT:
        """Execute this method.

        Args:
            tf: The data to run the method against. `None` for generative methods (e.g. derivation).
            config: Configuration parameters for the method.

        Returns:
            Result of running the method. Type depends on the operation family.
        """
        pass


def observation_interval(config: DataProcessingMethodConfig) -> tuple[datetime, datetime | None] | None:
    """Resolve the observation interval a method should be restricted to, from its configuration.

    Args:
        config: Configuration parameters for the method.

    Returns:
        A (start, end) tuple, or None if the config declares no start date.
    """
    if config.start_date is None:
        return None
    return config.start_date, config.end_date

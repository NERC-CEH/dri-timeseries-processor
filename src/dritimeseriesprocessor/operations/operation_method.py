"""Shared method classes for all operation families (correction, QC, infill, aggregation, derivation)."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar, Generic, TypeVar

import time_stream as ts
from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import ConfigurationType

ResultT = TypeVar("ResultT")


class OperationMethod(Operation, ABC):
    """Base class for a single operation method, which a pipeline looks up by name and runs."""

    operation_type: ClassVar[ConfigurationType]


class TransformMethod(OperationMethod, ABC, Generic[ResultT]):
    """A method that works on existing data: run(tf, config) -> result.

    The result type depends on the operation family: corrections, infilling and aggregation return a new
    `TimeFrame`, while QC returns a boolean pass/fail mask.
    """

    @abstractmethod
    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ResultT:
        """Execute this method.

        Args:
            tf: The data to run the method against.
            config: Configuration parameters for the method.

        Returns:
            Result of running the method.
        """
        pass


class GenerativeMethod(OperationMethod, ABC):
    """A method that builds new data rather than working on existing data: run(config) -> TimeFrame.

    Everything it needs comes from its configuration, including the input datasets the pipeline puts there.
    """

    @abstractmethod
    def run(self, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        """Execute this method.

        Args:
            config: Configuration parameters for the method, including its input data.

        Returns:
            The TimeFrame this method builds.
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

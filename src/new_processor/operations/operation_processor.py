"""
An orchestration class used to run for processing operations for corrections, quality control and infilling.
"""

import copy
import logging
from abc import ABC, abstractmethod
from typing import Iterable, TypeVar

import time_stream as ts
from time_stream.exceptions import FlagSystemNotFoundError

from new_processor.routers.metadata.local_loader import fetch_methods
from new_processor.models.api_models.operations.operation import OperationDescriptor
from new_processor.models.domain_models.processing_config import MethodConfig, ProcessingConfig
from new_processor.models.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import OperationType

logger = logging.getLogger(__name__)


T = TypeVar("T")
U = TypeVar("U")


class OperationProcessor(ABC):
    """A base class to define the workflow of operations such as corrections, QC, and infilling.

    Subclasses implement the operation specific components such as applying a method, computing flag masks,
    sorting configuration blocks, and constructing flag column names.
    """

    def __init__(
            self,
            operation_type: OperationType,
            flag_system_name: str
    ):
        """Initialise the operation processor.

        Args:
            operation_type: Type of operation.
            flag_system_name: Name of the flag system to use for this operation.
        """
        self.operation_type = operation_type
        self.flag_system_name = flag_system_name
        self.registry = fetch_methods(operation_type)

    @abstractmethod
    def apply_method(
            self,
            tf: ts.TimeFrame,
            method_metadata: OperationDescriptor,
            config: MethodConfig,
            dataset_repository: dict[str, TimeSeriesContainer]
    ) -> T:
        """Apply a specific method to the time series data.

        Args:
            tf: Time series frame to process.
            method_metadata: Metadata describing the method to apply.
            config: Configuration object containing method parameters.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Result of applying the method, format depends on implementation.
        """
        pass

    @abstractmethod
    def compute_flag_mask(self, tf: ts.TimeFrame, result: T, column_name: str) -> U:
        """Compute a boolean mask indicating which values should be flagged.

        Args:
            tf: Original TimeFrame being processed.
            result: Result from applying a method to tf.
            column_name: Name of the column being processed.

        Returns:
            Boolean mask suitable as use in a Polars expression for flagging.
        """
        pass

    @abstractmethod
    def get_configs(self, container: TimeSeriesContainer) -> Iterable[ProcessingConfig]:
        """Extract the method configuration blocks for this operation.

        Args:
            container: Time series container of metadata and data.

        Returns:
            List of configuration blocks to be applied.
        """
        pass

    @abstractmethod
    def get_flag_column(self, column: str) -> str:
        """Determine the flag column name for a given data column.

        Args:
            column: Name of the data column.

        Returns:
            Name of the corresponding flag column.
        """
        pass

    @abstractmethod
    def core_flag_updater(self, tf: ts.TimeFrame):
        """Update core flags after all methods are applied.

        Args:
            tf: TimeFrame with flags to update.

        Returns:
            Timeframe with updated core flags
        """
        pass

    @staticmethod
    def configure_parameters(method_metadata: OperationDescriptor, params: dict) -> dict:
        """Configure method parameters by applying mappings and defaults.

        Args:
            method_metadata: Metadata describing the method to apply.
            params: Dictionary of parameters to configure.

        Returns:
            Configured parameters dictionary with remapped names and defaults.
        """

        # Remap config parameter names if required
        for old, new in method_metadata.arg_mapping.items():
            if old in params:
                params[new] = params.pop(old)

        # Add default kwargs
        params.update(method_metadata.kwargs)

        return params

    def sort_configs(self, configs: Iterable[ProcessingConfig]) -> Iterable[ProcessingConfig]:
        """Sort configuration blocks into execution order.

        Override this method in subclasses to define custom ordering logic.

        Args:
            configs: List of configuration blocks.

        Returns:
            Sorted list of configuration blocks
        """
        return configs

    def run(self, container: TimeSeriesContainer, dataset_repository: dict[str, TimeSeriesContainer]) -> ts.TimeFrame:
        """Execute the full operation workflow on the time series container.

        Args:
            container: Time series container of metadata and data for the primary dataset to process.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            The updated TimeFrame after all operations and flag updates.
        """
        # 1. Extract available methods from registry
        methods = self.registry.items
        tf_primary = container.data
        col_primary = tf_primary.metadata["column_name"]

        # 2. Initialise flag system
        flag_system = {name: m.id for name, m in methods.items()}
        try:
            tf_primary.get_flag_system(self.flag_system_name)
        except FlagSystemNotFoundError:
            tf_primary.register_flag_system(self.flag_system_name, flag_system)

        # 3. Prepare flag column
        flag_column = self.get_flag_column(col_primary)
        if flag_column not in tf_primary.flag_columns:
            tf_primary.init_flag_column(col_primary, self.flag_system_name, flag_column)

        # 4. Extract the configs to run
        configs = self.get_configs(container)
        configs = self.sort_configs(configs)

        # 5. Apply configs
        for cfg_block in configs:
            for cfg in cfg_block.method_configs:
                logger.info(f"Operation: {self.operation_type} | {cfg.method}")

                # Create a copy to ensure that any mutations that take place are self-contained.
                cfg = copy.copy(cfg)

                # Extract the method metadata and configure the parameters
                method_metadata = methods[cfg.method]
                cfg.params = self.configure_parameters(method_metadata, cfg.params)

                # Run the method!
                result = self.apply_method(tf_primary, method_metadata, cfg, dataset_repository)

                # Add any resulting flags
                mask = self.compute_flag_mask(tf_primary, result, col_primary)
                if mask is not None:
                    tf_primary.add_flag(flag_column, cfg.method, mask)

        # 6. Post-process core flags
        tf_primary = self.core_flag_updater(tf_primary)

        return tf_primary

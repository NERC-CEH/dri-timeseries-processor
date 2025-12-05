import logging
from abc import ABC, abstractmethod

from time_stream.exceptions import FlagSystemNotFoundError

from new_processor.api_models.operations.operation import OperationRegistry
from new_processor.domain_models.time_series_container import TimeSeriesContainer
from new_processor.utils.enums import OperationType

logger = logging.getLogger(__name__)


class OperationProcessor(ABC):
    """A base class to define the workflow of operations such as corrections, QC, and infilling.
    """

    def __init__(
            self,
            operation_type: OperationType,
            flag_system_name: str,
            registry: OperationRegistry,
    ):
        self.operation_type = operation_type
        self.flag_system_name = flag_system_name
        self.registry = registry

    @abstractmethod
    def apply_method(self, tf, method_metadata, config, dataset_repository):
        pass

    @abstractmethod
    def compute_flag_mask(self, tf, result, column_name):
        pass

    @abstractmethod
    def get_configs(self, container: TimeSeriesContainer):
        pass

    @abstractmethod
    def get_flag_column(self, column: str):
        pass

    @abstractmethod
    def core_flag_updater(self, tf):
        pass

    def sort_configs(self, configs):
        return configs

    def run(self, container, dataset_repository):
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
        configs = self.sort_configs(configs)  # Child class determines any ordering

        # 5. Apply configs
        for cfg_block in configs:
            for cfg in cfg_block.method_configs:
                logger.info(f"Operation: {self.operation_type} | {container.ts_id} | {cfg.method}. ")

                method_metadata = methods[cfg.method]

                result = self.apply_method(tf_primary, method_metadata, cfg, dataset_repository)

                mask = self.compute_flag_mask(tf_primary, result, col_primary)
                if mask is not None:
                    tf_primary.add_flag(flag_column, cfg.method, mask)

        # 6. Post-process flags (core flag updater)
        tf_primary = self.core_flag_updater(tf_primary)

        return tf_primary

"""
An orchestration class used to run for processing operations for corrections, quality control and infilling.
"""

import logging
from abc import ABC, abstractmethod

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.flags.flag_methods import ensure_flag_column
from dritimeseriesprocessor.utils.enums import ConfigurationType, FlagRole

logger = logging.getLogger(__name__)


class OperationPipeline(ABC):
    """A base class to define the workflow of operations such as corrections, QC, and infilling.

    Subclasses implement the operation specific components such as applying a method, computing flag masks and
    updating core flags.
    """

    # Role of the flag column this operation writes during processing (e.g. the QC flag column for quality control).
    # Operations that do not produce their own flags (aggregation, derivation) leave this as None.
    flag_role: FlagRole | None = None

    def __init__(self, operation_type: ConfigurationType, flag_systems: dict[str, dict[str, int]]):
        """Initialise the operation processor.

        Args:
            operation_type: Type of operation.
            flag_systems: Flag systems to register on the result before updating core flags.
        """
        self.operation_type = operation_type
        self.flag_systems = flag_systems
        # Flag column names of the dataset being processed, keyed by role. Set at the start of `run`.
        self.flag_column_roles: dict[FlagRole, str] = {}

    @abstractmethod
    def apply(
        self,
        tf: ts.TimeFrame | None,
        config: DataProcessingMethodConfig,
        dataset_repository: dict[str, TimeSeriesContainer],
    ) -> ts.TimeFrame:
        """Apply a specific method to the time series data.

        Args:
            tf: Time series frame to process, or `None` for generative operations (e.g. derivation) that
                build their result from `config.params` instead.
            config: Configuration that the method requires.
            dataset_repository: Repository for accessing additional datasets.

        Returns:
            Result of applying the method, format depends on implementation.
        """
        pass

    def get_flag_column(self) -> str | None:
        """Get the name of the flag column this operation writes during processing.

        Returns:
            Name of the flag column, or None if this operation does not produce flags or the dataset does not declare
            a flag column for it.
        """
        if self.flag_role is None:
            return None
        return self.flag_column_roles.get(self.flag_role)

    @abstractmethod
    def compute_flag_mask(self, tf: ts.TimeFrame, result: ts.TimeFrame, column_name: str) -> pl.Series | pl.Expr:
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
    def core_flag_updater(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """Update core flags after all methods are applied.

        Args:
            tf: TimeFrame with flags to update.

        Returns:
            Timeframe with updated core flags
        """
        pass

    def run(
        self,
        container: TimeSeriesContainer,
        dataset_repository: dict[str, TimeSeriesContainer],
        config: DataProcessingConfig,
    ) -> ts.TimeFrame:
        """Execute the full operation workflow on the time series container.

        Args:
            container: Time series container of metadata and data for the primary dataset to process.
            dataset_repository: Repository for accessing additional datasets.
            config: The data processing configuration to run.

        Returns:
            The updated TimeFrame after all operations and flag updates.
        """
        tf = container.data
        self.flag_column_roles = container.flag_column_roles

        # Operations that process existing data write their flags onto it during ``apply`` (e.g. a correction writes
        # the corrections flag column), so make sure those flag columns exist first.
        # Generative operations (e.g. aggregation, derivation) start without data here and build a fresh TimeFrame
        # in apply, so there is nothing to set up yet.
        if tf is not None and container.has_flags():
            self._init_flag_columns(tf, container.flag_column_schemes)

        # Apply configs
        for cfg in config.method_configs:
            logger.info(f"Operation: {self.operation_type} | {cfg.method}")

            # Run the method. Generative operations (e.g. aggregation, derivation) accept tf=None and build a
            # fresh TimeFrame; every other operation receives the existing data set up above.
            tf = self.apply(tf=tf, config=cfg, dataset_repository=dataset_repository)
            tf = self.apply_rounding(tf, cfg)

        # Every operation applies at least one method, so by this point tf is always a real TimeFrame.
        if tf is None:
            raise ValueError(f"Operation {self.operation_type} produced no data for: {container.ts_id}")

        if container.has_flags():
            # Generative operations (e.g. aggregation, derivation) built a new TimeFrame during ``apply`` with no
            # flagging, so set up its flag columns before updating core flags.
            # This is a "no-op" when this was already done before the loop.
            self._init_flag_columns(tf, container.flag_column_schemes)

            # Update core flags
            tf = self.core_flag_updater(tf)

        # Ensure time column name of tf is same as container's (not set for ObservationDatasets)
        if container.time_column_name is not None:
            tf = tf.rename_time_column(container.time_column_name)

        return tf

    def _init_flag_columns(self, tf: ts.TimeFrame, flag_column_schemes: dict[str, str]) -> None:
        """Create every flag column the dataset defines on the result TimeFrame.

        This includes flag columns for operations that are not in the dataset's plan (e.g. a derived dataset with no
        infill step still gets its infill flag column), so every saved dataset has the full set of flag columns
        defined in its metadata. Flag columns that already exist are left untouched.

        Args:
            tf: The result TimeFrame to set up flag columns on.
            flag_column_schemes: Flag column names mapped to the flag system that they relate to.
        """
        for flag_column in flag_column_schemes:
            ensure_flag_column(tf, flag_column, self.flag_systems, flag_column_schemes)

    def _add_flag(self, tf: ts.TimeFrame, result: ts.TimeFrame, col_name: str, flag_name: str) -> None:
        """Apply a flag to the flag column

        Args:
            tf: TimeFrame containing original data.
            result: The result of the operation.
            col_name: Name of the parent column.
            flag_name: Type of flag to apply (must exist in the associated flag system).
        """
        flag_column = self.get_flag_column()
        if flag_column is None or flag_column not in tf.flag_columns:
            return

        mask = self.compute_flag_mask(tf, result, col_name)
        if mask is not None:
            result.add_flag(flag_column, flag_name, mask)

    @staticmethod
    def _inject_dependency_timeframes(
        config: DataProcessingMethodConfig,
        dataset_repository: dict[str, TimeSeriesContainer],
        keys: tuple[str, ...] = (),
    ) -> None:
        """Inject each dependency's TimeFrame into `config.params`.

        Named inputs in `config.inputs` are added under their input name, so a method's `run`/`expr` can refer to
        them by the names it expects, e.g. `config.params["swin"]`.

        Dependency ids in `config.params` under the given `keys` (each may hold a single id string or a list of ids)
        are added under the dependency's lowercased source column name.

        Args:
            config: Configuration whose inputs and params supply dependency ids, and whose params receive the
                injected TimeFrames.
            dataset_repository: Repository for accessing dependency containers.
            keys: Names of the `config.params` entries that hold dependency dataset ids, if any.
        """
        dep_ids: list[str] = []
        for key in keys:
            values = config.params.get(key) or []
            if isinstance(values, str):
                dep_ids.append(values)
            else:
                dep_ids.extend(values)

        for dep_id in dep_ids:
            dep_container = dataset_repository[dep_id]
            if dep_container.source_column:
                config.params[dep_container.source_column.lower()] = dep_container.data

        for input_name, dataset_id in config.inputs.items():
            config.params[input_name] = dataset_repository[dataset_id].data

    @staticmethod
    def apply_rounding(tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        """Apply any rounding to the resulting TimeFrame data (if required by metadata)

        Args:
            tf: TimeFrame containing data to round.
            config: Configuration options containing round parameter.

        Returns:
            TimeFrame with rounded data.
        """
        round_decimals: int | None = config.params.get("round")
        if round_decimals is None:
            return tf

        col_name = tf.metadata["column_name"]
        return tf.with_df(tf.df.with_columns(pl.col(col_name).round(round_decimals).alias(col_name)))

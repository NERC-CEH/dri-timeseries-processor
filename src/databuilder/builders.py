import datetime
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from databuilder.enums import Operator


class BaseBuilder(ABC):
    """Base builder class for manipulating a dataframe"""

    @property
    def target(self) -> Path:
        """The target parquet file"""
        return self._target

    @target.setter
    def target(self, path: Tuple[os.PathLike | str] | os.PathLike | str) -> None:
        """Sets the target parameter

        Args:
            path: Path to set the target to. If a single value is given, the target
            will be set and the _output set to the same value. If a tuple of two elements
            is given, the target will be set as the same element, and the _output the
            second"""

        output = None

        if isinstance(path, tuple):
            target, output = path
        else:
            target = path

        if not isinstance(target, Path):
            target = Path(target)

        if not target.exists():
            raise FileNotFoundError(f"Parquet file: '{path}' does not exist")

        if not output:
            self._output = target
        else:
            if not isinstance(output, Path):
                output = Path(output)
            self._output = output

        self._target = target
        self._load_data()

    _output: os.PathLike
    """The output destination, defaults to the target"""

    _dataframe: Optional[pd.DataFrame] = None
    """The internal dataframe that work is done on"""

    def __init__(self, target: os.PathLike | str, output: Optional[os.PathLike | str] = None):
        """Initializes the instance

        Args:
            target: The target parquet file
            output: The output file, defaults to the target
        """

        self.target = (target, output)

    @abstractmethod
    def _load_data(self) -> None:
        """Loads the data into a dataframe"""

    def reset(self) -> None:
        """Resets the builder"""

        self._dataframe = None

    def set_random_cells_to_null(self, percent: int | float, exclude: Optional[List[str]] = None) -> None:
        """Sets random cells to NULL based of a percentage probability

        The randomness is set on each column separately. It does not clear full rows.

        Args:
            percent: The percentage of rows to change for each variable
            exclude: A list of columns to exclude.
        """

        if not isinstance(percent, (int, float)):
            percent = float(percent)

        if percent < 0 or percent > 100:
            raise ValueError(f"'percent' must be from 0 - 100, not {percent}")

        target_columns = self._dataframe.columns

        if exclude:
            target_columns = [col for col in target_columns if col not in exclude]

        for col in target_columns:
            non_nan_indexes = self._dataframe[self._dataframe[col].notnull()]

            nan_indexes = non_nan_indexes.sample(frac=percent / 100).index
            self._dataframe.loc[nan_indexes, col] = np.nan

    def clear_percentage_of_rows(self, percent: int | float) -> None:
        """Removes a given percentage of rows randomly

        Args:
            percent: The percentage of rows to remove from 0 - 100
        """

        if not isinstance(percent, (int, float)):
            percent = float(percent)

        if percent < 0 or percent > 100:
            raise ValueError(f"'percent' must be from 0 - 100, not {percent}")

        self._dataframe = self._dataframe.drop(self._dataframe.sample(frac=percent / 100).index)

    def filter_by_time(self, time: datetime.time, operator: Operator, datetime_col: str = "time") -> None:
        """Selects rows relative to a given date or time.

        Args:
            time: The datetime object specifying the selection point
            operator: The comparison operation to apply [>, >=, <, <=, ==]
                ">" overwrites the parquet file with only values AFTER the
                specified time
            datetime_col: The column name where the datetime is found
        """

        if not isinstance(operator, Operator):
            raise TypeError(f"'operator' must be an Operator, not {type(operator)}")

        if not isinstance(time, datetime.time):
            raise TypeError(f"'time' must be a datetime.time, not {type(time)}")

        self._dataframe = self._dataframe.query(f"{datetime_col}.dt.time {operator} @pd.Timestamp('{time}').time()")

    @abstractmethod
    def write_output(self, new_dir_ok: bool = False) -> None:
        """Writes the result from the builder

        Args:
            new_dir_ok: Allows creation in non-existing directory if True,
            raises an exception if False

        Raises:
            NotADirectoryError: If directory not exists and `new_dir_ok`=False
        """

    def build_all(
        self,
        row_removal_percent: Optional[int | float] = None,
        cell_removal_percent: Optional[int | float] = None,
        clear_before_time: Optional[datetime.time] = None,
        clear_after_time: Optional[datetime.time] = None,
        protected_columns: Optional[List[str]] = None,
    ) -> None:
        """Builds using all methods using the provided values

        Args:
            row_removal_percent: Percentage of rows to remove.
            cell_removal_percent: Percentage of cells to remove
            clear_before_time: Clears cells before the given time '>=' remains
            clear_after_time: Clears cells after the given time '<=' remains
            protected_columns: Columns to protect from nulling."""

        if row_removal_percent:
            self.clear_percentage_of_rows(row_removal_percent)

        if cell_removal_percent:
            self.set_random_cells_to_null(cell_removal_percent, exclude=protected_columns)

        if clear_before_time:
            self.filter_by_time(clear_before_time, Operator.GREATER_THAN_EQUAL)

        if clear_after_time:
            self.filter_by_time(clear_after_time, Operator.LESS_THAN_EQUAL)


class ParquetBuilder(BaseBuilder):
    """Concrete implementation of the BaseBuilder class for manipulating
    a parquet file"""

    def _load_data(self) -> None:
        """Loads the data into a dataframe

        Args:
            src: The source file.
        """
        self._dataframe = pd.read_parquet(self.target)

    def write_output(self, new_dir_ok: bool = False) -> None:
        """Writes the result from the builder

        Args:
            new_dir_ok: Allows creation in non-existing directory if True,
            raises an exception if False

        Raises:
            NotADirectoryError: If directory not exists and `new_dir_ok`=False
        """

        if not self._output.parent.exists():
            if not new_dir_ok:
                raise NotADirectoryError(
                    (
                        "Can't write parquet, output directory doesn't exist and",
                        f"the `new_dir_ok` flag is False: '{self._output}'",
                    )
                )
            os.makedirs(self._output.parent)

        self._dataframe.to_parquet(self._output)

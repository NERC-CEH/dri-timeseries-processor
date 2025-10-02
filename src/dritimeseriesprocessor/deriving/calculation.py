import logging
from abc import ABC, abstractmethod
from typing import Optional, Union

import polars as pl
import time_stream as ts
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class AggregationConfig:
    function_name: str
    period: ts.Period


class Calculation(ABC):
    def __init__(self, name: str, column_name: Optional[str] = None, units: Optional[str] = None):
        """Abstract base class for different types of calculations.

        The rationale for abstracting Calculations into a class like this is to take advantage of Polars expression
        chaining. Some Calculations are nested, e.g. calculating 1 thing requires the calculation of several other
        things - by using Polars expressions we can make this more efficient, as Polars will look to optimise all
        the expressions together before finally evaluating the calculation (lazy evaluation).

        Args:
            name: Name of the calculation.
            column_name: Custom name for the derived column. If None, will be set to the class default.
            units: Units of the calculated value.
        """
        self._name = name
        self._column_name = column_name
        self._units = units

    @property
    def name(self) -> str:
        return self._name

    @property
    def column_name(self) -> str:
        return self._get_final_column_name(self._column_name)

    @property
    def units(self) -> str:
        return self._units

    @property
    def dependencies(self) -> list["Calculation"]:
        return self._collect_dependencies()

    @property
    def preprocess_aggregation_config(self) -> AggregationConfig | None:
        return None

    @property
    def postprocess_aggregation_config(self) -> AggregationConfig | None:
        return None

    @property
    @abstractmethod
    def default_column_name(self) -> str:
        """Default column name for the calculation."""
        pass

    @abstractmethod
    def expr(self) -> pl.Expr:
        """Polars expression representing the calculation."""
        pass

    @staticmethod
    def _columns_to_expressions(*args: Union[str, pl.Expr]) -> Union[pl.Expr, list[pl.Expr]]:
        """Convert column name strings into Polars expressions if they are not already.

        Args:
            *args:  Any number of column names.  If strings, will be converted to: pl.col(<column name>)

        Returns:
            List of polars Col expressions

        Raises:
            TypeError if argument not a string or polars expression
        """
        invalid_args = [(arg, type(arg)) for arg in args if not isinstance(arg, (str, pl.Expr))]
        if invalid_args:
            raise TypeError(f"Arguments must be string or pl.Expr, got: {invalid_args}")

        input_as_expressions = [arg if isinstance(arg, pl.Expr) else pl.col(arg) for arg in args]
        if len(input_as_expressions) == 1:
            return input_as_expressions[0]
        return input_as_expressions

    def _get_final_column_name(self, column_name: Optional[str]) -> str:
        """Determine the final column name to be used for the result of the calculation.

        Args:
            column_name: Custom column name provided by the user.  If not provided, will use class defined default.

        Returns:
            str: Final column name to be used.
        """
        return column_name or self.default_column_name

    def evaluate(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """Evaluate the expression and perform any pre- and post- aggregations

        Args:
            tf: Input ts.TimeFrame.

        Returns:
            ts.TimeFrame: ts.TimeFrame with the result of the calculation.
        """

        if self.preprocess_aggregation_config:
            tf = self._apply_aggregation(tf, self.preprocess_aggregation_config)

        tf = self._evaluate_expression(tf=tf)

        if self.postprocess_aggregation_config:
            tf = self._apply_aggregation(tf, self.postprocess_aggregation_config)

        # Pull out time and self.column_name from the result
        tf = tf.select(self.column_name)

        return tf

    def _apply_aggregation(self, tf: ts.TimeFrame, aggregation_config: AggregationConfig) -> ts.TimeFrame:
        """Apply aggregation to the ts.TimeFrame DataFrame.

        Args:
            tf: Input ts.TimeFrame object.
            aggregation_config: The aggregation function to be applied and associated config.

        Returns:
            ts.TimeFrame: ts.TimeFrame with aggregated results.

        """
        aggregated_tf = tf.aggregate(
            aggregation_period=aggregation_config.period,
            aggregation_function=aggregation_config.function_name,
            columns=self.column_name,
        )

        # Rename to the original column name
        aggregated_column_name = f"{aggregation_config.function_name}_{self.column_name}"
        aggregated_tf = aggregated_tf.with_df(aggregated_tf.df.rename({aggregated_column_name: self.column_name}))
        return aggregated_tf

    def _evaluate_expression(self, tf: ts.TimeFrame) -> ts.TimeFrame:
        """
        Evaluate the expressions for the calculation, returning a new ts.TimeFrame with the results.

        Args:
            tf: Input ts.TimeFrame.

        Returns:
            ts.TimeFrame: ts.TimeFrame with the results of the calculation.
        """

        # Perform the evaluation(s)
        lazy_df = tf.df.lazy()
        result = lazy_df.with_columns(self.expr().alias(self.column_name))
        result_df = result.collect()

        return tf.with_df(result_df)

    def _collect_dependencies(self) -> list["Calculation"]:
        """Automatically discover dependencies by introspecting attributes that are instances of Calculation.

        Returns:
            A list of Calculation instances that this calculation depends on.
        """
        dependencies_types = set()
        dependencies = []

        def __collect_dependencies(calc: "Calculation") -> None:
            """Recursive method for getting dependencies of this calculation"""
            for attr_value in calc.__dict__.values():
                # Check if the attribute is a Calculation instance
                if isinstance(attr_value, Calculation):
                    # Check if this Calculation instance type is already represented
                    if type(attr_value) in dependencies_types:
                        return

                    # Add this calculation as a dependency
                    dependencies_types.add(type(attr_value))
                    dependencies.append(attr_value)

                    # Get any further dependencies
                    __collect_dependencies(attr_value)

        __collect_dependencies(self)
        return dependencies

    def __repr__(self):
        return f"Calculation({self.__class__.__name__})"

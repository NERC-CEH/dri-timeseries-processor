from abc import ABC, abstractmethod
from typing import Optional, Union

import polars as pl
from time_stream import Period, TimeSeries, aggregation  # noqa: F401


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
    def preprocess_aggregation_method(self) -> str | None:
        return None

    @property
    def preprocess_aggregation_period(self) -> str | None:
        return None

    @property
    def preprocess_aggregation_columns(self) -> Union[list, str]:
        return self.column_name

    @property
    def postprocess_aggregation_method(self) -> str | None:
        return None

    @property
    def postprocess_aggregation_period(self) -> str | None:
        return None
    
    @property
    def postprocess_aggregation_columns(self) -> Union[list, str]:
        return self.column_name

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

    def evaluate(
        self, ts: TimeSeries, include_dependency_columns: bool = False, allow_override: bool = False
    ) -> pl.DataFrame:
        """Evaluate the calculation, adding the result as a new column in the DataFrame.

        Args:
            df: Input DataFrame.
            include_dependency_columns: Whether to include results of dependent calculations of this
                                        calculation as columns in output df.
            allow_override: Whether to allow columns to be overridden by the calculation.

        Returns:
            pl.DataFrame: DataFrame with the result of the calculation.
        """
        if self.preprocess_aggregation_method:
            ts = self._apply_aggregation(
                ts,
                self.preprocess_aggregation_period,
                self.preprocess_aggregation_method,
                self.preprocess_aggregation_columns
            )

        ts = self._evaluate_expressions(
            ts=ts,
            include_dependency_columns=include_dependency_columns,
            allow_override=allow_override,
        )

        if self.postprocess_aggregation_method:
            ts = self._apply_aggregation(
                ts,
                self.postprocess_aggregation_period,
                self.postprocess_aggregation_method,
                self.postprocess_aggregation_columns
            )

        return ts

    def _apply_aggregation(self, ts: TimeSeries, aggregation_period: Period, aggregation_function: str, columns: Union[list, str]) -> pl.DataFrame:
        """Apply aggregation to the TimeSeries DataFrame.

        Args:
            ts: Input TimeSeries object.
            aggregation_function: Method to use for aggregation.
            aggregation_period: Period over which to aggregate.

        Returns:
            pl.DataFrame: DataFrame with aggregated results.
        """

        aggregated_ts = ts.aggregate(
            aggregation_period=aggregation_period,
            aggregation_function=aggregation_function,
            columns=columns
        )
        aggregated_column_name = f"{aggregation_function}_{self.column_name}"
        # Rename to the original column name
        aggregated_ts.df = aggregated_ts.df.rename({aggregated_column_name: self.column_name})

        #self._aggregated = self._columns_to_expressions(aggregated_column_name)
        return aggregated_ts

    def _evaluate_expressions(
        self, ts: TimeSeries, include_dependency_columns: bool = False, allow_override: bool = False
    ) -> TimeSeries:
        # Collect the expressions that we want to evaluate
        if include_dependency_columns:
            expressions = self._collect_expressions()
        else:
            expressions = {self.column_name: self.expr().alias(self.column_name)}

        # Check for existing columns in the DataFrame
        existing_columns = set(expressions.keys()) & set(ts.columns)
        if existing_columns and not allow_override:
            raise UserWarning(f"Columns already exist in DataFrame: {existing_columns}")

        # Perform the evaluation(s)
        lazy_df = ts.df.lazy()
        result = lazy_df.with_columns(list(expressions.values()))
        result_df = result.collect()

        # Pull out time and self.column_name from the result
        result_df = result_df.select([ts.time_name, self.column_name])

        return TimeSeries(
            df=result_df,
            time_name=ts.time_name,
            resolution=ts.resolution,
            periodicity=ts.periodicity,
            metadata=ts.metadata(),
        )

    def _collect_expressions(self) -> dict[str, pl.Expr]:
        """Collect all expressions required for the calculation, including dependencies.

        Returns:
            A dictionary mapping column names to their corresponding Polars expressions.
        """
        expressions = {}

        def __collect_expressions(calc: "Calculation") -> None:
            """Recursive method for getting expressions from dependencies"""
            if calc in expressions:
                return

            # Add the calc expression to the dict
            expressions[calc.column_name] = calc.expr().alias(calc.column_name)

            # Collect from dependencies
            for dep in calc._collect_dependencies():
                __collect_expressions(dep)

        __collect_expressions(self)
        return expressions

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

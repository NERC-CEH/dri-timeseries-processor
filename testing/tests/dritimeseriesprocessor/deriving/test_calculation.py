from typing import Any

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.deriving.derivations import Calculation
from testing.utils.testing_utils import df_to_ts


# Define some test Calculation classes that have a mix of dependencies in their calculation operations
class Parent(Calculation):
    # Multiple dependencies, nested.
    def __init__(self):
        super().__init__("Parent Calculation Class", "parent", "test_unit")
        self.child1 = Child1()  # Has no deps
        self.child2 = Child2()  # Has dep on Grandchild
        self.child3 = Child3()  # Has dep on Child1 and Grandchild
        self.child4 = Child4()  # Has dep on Child2 (and so the nested Grandchild)

    @property
    def default_column_name(self) -> str:
        return "parent"

    def expr(self) -> pl.Expr:
        return self.child1.expr() / self.child2.expr() - self.child4.expr()


class Child1(Calculation):
    # Zero dependencies
    def __init__(self):
        super().__init__("Child 1 Calculation Class", "child1", "test_unit")

    @property
    def default_column_name(self) -> str:
        return "child1"

    def expr(self) -> pl.Expr:
        return pl.col("col1") * 2


class Child2(Calculation):
    # 1 dependency
    def __init__(self):
        super().__init__("Child 2 Calculation Class", "child2", "test_unit")
        self.grandchild = Grandchild()

    @property
    def default_column_name(self) -> str:
        return "child2"

    def expr(self) -> pl.Expr:
        return self.grandchild.expr() / 10


class Child3(Calculation):
    # Multiple dependencies, each of which have no dependencies
    def __init__(self):
        super().__init__("Child 3 Calculation Class", "child3", "test_unit")
        self.child1 = Child1()
        self.grandchild = Grandchild()

    @property
    def default_column_name(self) -> str:
        return "child3"

    def expr(self) -> pl.Expr:
        return self.child1.expr() * self.grandchild.expr()


class Child4(Calculation):
    # Simple nested dependencies (1 dep has 1 dep)
    def __init__(self):
        super().__init__("Child 4 Calculation Class", "child4", "test_unit")
        self.child2 = Child2()

    @property
    def default_column_name(self) -> str:
        return "child4"

    def expr(self) -> pl.Expr:
        return self.child2.expr() + 2


class Grandchild(Calculation):
    # Zero dependencies
    def __init__(self):
        super().__init__("Grandchild Calculation Class", "grandchild", "test_unit")

    @property
    def default_column_name(self) -> str:
        return "grandchild"

    def expr(self) -> pl.Expr:
        return pl.col("col2") + 5


class TestEvaluate:
    def test_one_dependencies(self) -> None:
        """Test evaluation of a simple Calculation, which has no dependencies"""
        ts = df_to_ts(pl.DataFrame({"col1": [1, 2, 3]}))
        expected = df_to_ts(pl.DataFrame({"child1": [2, 4, 6]}))

        calc = Child1()
        result = calc.evaluate(ts)
        assert_frame_equal(result.df, expected.df)

    def test_muliple_dependencies(self) -> None:
        """Test a calculation with muliple dependencies."""
        ts = df_to_ts(pl.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6]}))
        expected = df_to_ts(pl.DataFrame({"child2": [0.9, 1.0, 1.1]}))

        calc = Child2()
        result = calc.evaluate(ts)
        assert_frame_equal(result.df, expected.df)


class TestCollectDependencies:
    def test_no_dependencies(self) -> None:
        """Test a calculation with no dependencies returns an empty list."""
        calc = Child1()
        result = calc._collect_dependencies()
        assert result == []

    def test_single_dependencies(self) -> None:
        """Test a calculation with a single dependency, which in turn has no dependencies."""
        calc = Child2()
        result = calc._collect_dependencies()
        assert len(result) == 1
        assert isinstance(result[0], Grandchild)

    def test_multiple_dependencies(self) -> None:
        """Test a calculation with multiple dependencies that each have no dependencies."""
        calc = Child3()
        result = calc._collect_dependencies()
        assert len(result) == 2
        # Dependencies returned in order they were seen in the chain
        assert isinstance(result[0], Child1)
        assert isinstance(result[1], Grandchild)

    def test_nested_dependencies(self) -> None:
        """Test a calculation with a dependency, that in turn as its own dependencies."""
        calc = Child4()
        result = calc._collect_dependencies()
        assert len(result) == 2
        # Dependencies returned in order they were seen in the chain
        assert isinstance(result[0], Child2)
        assert isinstance(result[1], Grandchild)

    def test_complex_dependencies(self) -> None:
        """Test a calculation with complex dependencies, including nested dependencies and duplicates."""
        calc = Parent()
        result = calc._collect_dependencies()
        assert len(result) == 5
        # Dependencies returned in order they were seen in the chain
        assert isinstance(result[0], Child1)
        assert isinstance(result[1], Child2)
        assert isinstance(result[2], Grandchild)
        assert isinstance(result[3], Child3)
        assert isinstance(result[4], Child4)


class TestColumnsToExpressions:
    dummy_calc = Parent()

    def test_single_string_input(self) -> None:
        """Test that a single column string is returned as single expression."""
        col = "col1"
        result = self.dummy_calc._columns_to_expressions(col)
        assert isinstance(result, pl.Expr)
        assert result.meta.output_name() == col

    def test_multiple_string_inputs(self) -> None:
        """Test that multiple column strings are returned as a list of expressions."""
        cols = ["col1", "col2", "col3"]
        result = self.dummy_calc._columns_to_expressions(*cols)
        assert isinstance(result, list)
        assert len(result) == len(cols)
        for idx, col_name in enumerate(cols):
            assert isinstance(result[idx], pl.Expr)
            assert result[idx].meta.output_name() == col_name

    def test_single_col_expression_input(self) -> None:
        """Test that a single column expression is returned as the same expression."""
        col = pl.col("col1")
        result = self.dummy_calc._columns_to_expressions(col)
        assert isinstance(result, pl.Expr)
        assert repr(result) == repr(col)
        assert result.meta.output_name() == col.meta.output_name()

    def test_multiple_col_expression_input(self) -> None:
        """Test that multiple column expressions are returned as a list of the same expressions."""
        cols = [pl.col("col1"), pl.col("col2"), pl.col("col3")]
        result = self.dummy_calc._columns_to_expressions(*cols)

        assert isinstance(result, list)
        assert len(result) == len(cols)
        for idx, expr in enumerate(cols):
            assert isinstance(result[idx], pl.Expr)
            assert repr(result[idx]) == repr(expr)
            assert result[idx].meta.output_name() == expr.meta.output_name()

    def test_single_math_expression_input(self) -> None:
        """Test that a single math expression is returned as the same expression."""
        col = (pl.col("col1") * 10) ** 2
        result = self.dummy_calc._columns_to_expressions(col)
        assert isinstance(result, pl.Expr)
        assert repr(result) == repr(col)

    def test_mixed_inputs(self) -> None:
        """Test a mix of string and expressions are returned as a list of equivalent expressions."""
        cols = [pl.col("col1"), "col2", (pl.col("col3") + 10)]
        result = self.dummy_calc._columns_to_expressions(*cols)

        assert isinstance(result, list)
        assert len(result) == len(cols)

        for expr in result:
            assert isinstance(expr, pl.Expr)

    def test_no_arguments(self) -> None:
        """Test that no arguments returns empty list"""
        result = self.dummy_calc._columns_to_expressions()
        assert result == []

    @pytest.mark.parametrize(
        "invalid_arg",
        [
            (5),
            (3.14),
            (None),
            (["a", "b", "c"]),
            ({"a": "colA", "b": "colB", "c": "colC"}),
        ],
        ids=["int", "float", "None", "list", "dict"],
    )
    def test_invalid_input(self, invalid_arg: Any) -> None:
        """Test that an invalid input (i.e. not string or expression) raises an exception."""
        with pytest.raises(TypeError):
            self.dummy_calc._columns_to_expressions(invalid_arg)

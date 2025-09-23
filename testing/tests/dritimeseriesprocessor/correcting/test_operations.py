from datetime import datetime
from typing import Any

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.correcting.operations import Add, LWCorrection, Operation, PACorrection, Power, Scalar
from testing.utils.testing_utils import create_test_filter, create_test_operation_ts


class TestOperation:
    @pytest.mark.parametrize(
        "get_input,input_args,expected",
        [
            ("add", {"correction_factor": 10}, Add),
            ("scalar", {"correction_factor": 2}, Scalar),
        ],
    )
    def test_get_with_string(self, get_input: str, input_args: dict[str, int], expected: Any) -> None:
        """Test Operation.get() with string input."""
        op = Operation.get(get_input, **input_args)
        assert isinstance(op, expected)
        for arg, val in input_args.items():
            assert getattr(op, arg) == val

    def test_get_with_bad_string(self) -> None:
        """Test Operation.get() with invalid string."""
        with pytest.raises(ValueError):
            Operation.get("bad_operation")


class TestAdd:
    @pytest.mark.parametrize(
        "factor,expected",
        [
            (100, [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0]),
            (0, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]),
            (-1, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
        ],
    )
    def test_add_simple(self, factor: int, expected: list[float]) -> None:
        """Test that the add function works across the full DataFrame"""
        ts = create_test_operation_ts()

        adder = Add(factor)

        expected_df = pl.DataFrame(
            {
                "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
                "value": expected,
            }
        )

        result = adder.apply(ts)

        assert_frame_equal(result.df, expected_df)

    @pytest.mark.parametrize(
        "factor,expected",
        [
            (100, [1.0, 2.0, 103.0, 104.0, 105.0, 6.0, 7.0]),
            (0, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]),
            (-1, [1.0, 2.0, 2.0, 3.0, 4.0, 6.0, 7.0]),
        ],
    )
    def test_date_filter(self, factor: int, expected: list[int]) -> None:
        """Test that the add function works with a date filter"""
        ts = create_test_operation_ts()
        date_filter = create_test_filter()

        adder = Add(factor)
        expected_df = pl.DataFrame(
            {
                "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
                "value": expected,
            }
        )

        result = adder.apply(ts, filter_expr=date_filter)

        assert_frame_equal(result.df, expected_df)


class TestScalar:
    @pytest.mark.parametrize(
        "factor,expected",
        [
            (2, [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0]),
            (1, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]),
            (0, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
            (-1, [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0, -7.0]),
            (0.5, [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]),
        ],
    )
    def test_scalar_simple(self, factor: int, expected: list[int]) -> None:
        """Test that the Scalar function works across the full DataFrame"""
        ts = create_test_operation_ts()

        multiplier = Scalar(factor)
        result = multiplier.apply(ts)
        expected_df = pl.DataFrame(
            {
                "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
                "value": expected,
            }
        )
        assert_frame_equal(result.df, expected_df)


class TestPower:
    @pytest.mark.parametrize(
        "factor,expected",
        [
            (2, [1.0, 4.0, 9.0, 16.0, 25.0, 36.0, 49.0]),
            (3, [1.0, 8.0, 27.0, 64.0, 125.0, 216.0, 343.0]),
            (1, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]),
            (0, [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]),
        ],
    )
    def test_power_simple(self, factor: int, expected: list[int]) -> None:
        """Test that the Power function works across the full DataFrame"""
        ts = create_test_operation_ts()

        power_op = Power(factor)
        expected_df = pl.DataFrame(
            {
                "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
                "value": expected,
            }
        )

        result = power_op.apply(ts)

        assert_frame_equal(result.df, expected_df)


class TestLWCorrection:
    def test_lw_correction_simple(self) -> None:
        """Test that the LWCorrection function works across the full DataFrame"""
        lw = create_test_operation_ts([373.9, 381.5, 386.9, 398.9, 387.7, 387.3, 391.8])
        lw_unc = create_test_operation_ts([-53.24, -56.31, -56.64, -41.11, -64.04, -75.39, -81.5])
        ta = create_test_operation_ts([20.33, 21.74, 22.79, 22.91, 24.3, 25.72, 27.27])
        factor = 1.00924

        expected_df = pl.DataFrame(
            {
                "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
                "value": [
                    366.89501779404736,
                    371.93855976840695,
                    377.7449872014795,
                    394.1243133190569,
                    379.22105814566305,
                    376.3027264419359,
                    379.5942580579116,
                ],
            }
        )

        lw_correction = LWCorrection(lw_unc, ta, factor)
        result = lw_correction.apply(lw)

        assert_frame_equal(result.df, expected_df)


class TestPACorrection:
    def test_pa_correction_simple(self) -> None:
        """Test that the PACorrection function works across the full DataFrame"""
        pa = create_test_operation_ts([1007.504, 1007.391, 1007.359, 1007.334, 1007.262, 1007.194, 1007.213])
        ta = create_test_operation_ts([12.25, 12.49, 12.58, 12.56, 12.82, 13.18, 13.31])
        altitude = 74.0
        factor = -5.1

        expected_df = pl.DataFrame(
            {
                "timestamp": [datetime(2025, m, 1) for m in range(1, 8)],
                "value": [1002.4489, 1002.3359, 1002.3039, 1002.2789, 1002.2069, 1002.1388, 1002.1578],
            }
        )

        pa_correction = PACorrection(ta, altitude, factor)
        result = pa_correction.apply(pa)

        assert_frame_equal(result.df, expected_df)

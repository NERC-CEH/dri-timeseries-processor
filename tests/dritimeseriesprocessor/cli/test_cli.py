import argparse
from collections import Counter
from datetime import date, datetime, timedelta

import pytest
from freezegun import freeze_time

from dritimeseriesprocessor.cli.cli import _parse_date_range, _parse_lookback, parse_args
from dritimeseriesprocessor.cli.selection import DimensionSelection
from dritimeseriesprocessor.utils.urls import SITE_URI


class TestParseArgs:
    @pytest.mark.parametrize(
        "selections, expected_queries",
        [
            (
                [["SITE1", "TA", "P1D"]],
                [
                    DimensionSelection(
                        network="a_network", sites=[f"{SITE_URI}/SITE1"], variables=["TA"], periodicities=["P1D"]
                    )
                ],
            ),
            (
                [["SITE1", "TA", "P1D"], ["SITE2", "RH", "PT30M"]],
                [
                    DimensionSelection(
                        network="a_network", sites=[f"{SITE_URI}/SITE1"], variables=["TA"], periodicities=["P1D"]
                    ),
                    DimensionSelection(
                        network="a_network", sites=[f"{SITE_URI}/SITE2"], variables=["RH"], periodicities=["PT30M"]
                    ),
                ],
            ),
        ],
    )
    def test_explicit_selection(self, selections: list, expected_queries: list) -> None:
        args = ["from-selection", "--network", "a_network"]
        for site_id, variable, periodicity in selections:
            args.extend(["--selection", site_id, variable, periodicity])

        cfg = parse_args(args)

        queries = cfg.selection
        assert Counter(queries) == Counter(expected_queries)

    @pytest.mark.parametrize(
        "selection",
        [
            "TA P1D",
            "SITE1 P1D",
            "SITE1 TA",
        ],
    )
    def test_explicit_selection_error(self, selection: str) -> None:
        """Test that not providing a dimension in an explicit selection raises an error"""
        args = ["--network", "a_network", "--selection"]
        args.extend(selection.split(" "))
        with pytest.raises(SystemExit):
            parse_args(args)

    @pytest.mark.parametrize(
        "selection",
        [
            "TA P1D",
            "SITE1 P1D",
            "SITE1 TA",
        ],
    )
    def test_explicit_selection_error_additional_args(self, selection: str) -> None:
        """Test that not providing a dimension in an explicit selection raises an error, even when followed by
        further args. This is to test that additional args aren't stolen as the 3rd argument."""
        args = ["--network", "a_network", "--selection"]
        args.extend(selection.split(" "))
        args.extend(["--end-date", "2025-01-01"])

        with pytest.raises(SystemExit):
            parse_args(args)

    def test_cross_product_all_specified(self) -> None:
        """Test that a cross product selection is created, when all dimensions are specified"""
        cfg = parse_args(
            [
                "from-cross-product",
                "--network",
                "a_network",
                "--sites",
                "SITE1",
                "SITE2",
                "--variables",
                "TA",
                "RH",
                "--periodicities",
                "P1D",
            ]
        )

        expected_queries = [
            DimensionSelection(
                network="a_network",
                sites=[f"{SITE_URI}/SITE1", f"{SITE_URI}/SITE2"],
                variables=["TA", "RH"],
                periodicities=["P1D"],
            )
        ]
        assert cfg.selection == expected_queries

    @pytest.mark.parametrize(
        "args, expected_queries",
        [
            (
                ["--variables", "TA"],
                [DimensionSelection(network="a_network", sites=None, variables=["TA"], periodicities=None)],
            ),
            (
                ["--sites", "SITE1"],
                [
                    DimensionSelection(
                        network="a_network", sites=[f"{SITE_URI}/SITE1"], variables=None, periodicities=None
                    )
                ],
            ),
            (
                ["--periodicities", "P1D"],
                [DimensionSelection(network="a_network", sites=None, variables=None, periodicities=["P1D"])],
            ),
        ],
    )
    def test_cross_product_with_missing_dimensions(self, args: list, expected_queries: list) -> None:
        cfg = parse_args(["from-cross-product", "--network", "a_network"] + args)
        assert cfg.selection == expected_queries

    def test_no_network_error(self) -> None:
        """Test that not providing a network raises an error"""
        with pytest.raises(SystemExit):
            parse_args(["--selection", "SITE1", "TA", "P1D"])

    @freeze_time("2025-01-01")
    def test_lookback_from_default(self) -> None:
        """Test that lookback works from the default end date"""
        cfg = parse_args(["from-cross-product", "--network", "a_network", "--lookback", "P2D"])
        assert cfg.end_date == datetime(2025, 1, 1)
        assert cfg.start_date == datetime(2024, 12, 30)

    @freeze_time("2025-01-01")
    def test_lookback_from_specified(self) -> None:
        """Test that lookback works from a specified end date"""
        cfg = parse_args(
            ["from-cross-product", "--network", "a_network", "--end-date", "2025-03-31", "--lookback", "P2D"]
        )
        assert cfg.end_date == datetime(2025, 3, 31)
        assert cfg.start_date == datetime(2025, 3, 29)

    def test_lookback_with_time_component_error(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(["--network", "a_network", "--lookback", "PT6H"])

    @pytest.mark.parametrize(
        "end_date_wrong",
        [
            "2025_03_31",
            "2025-3-31",
            "31st March 2025",
        ],
    )
    def test_end_date_incorrect_format(self, end_date_wrong: str) -> None:
        with pytest.raises(SystemExit):
            parse_args(["--network", "a_network", "--end-date", end_date_wrong])


class TestParseLookback:
    def test_valid_days(self) -> None:
        result = _parse_lookback("P2D")
        assert isinstance(result, timedelta)
        assert result == timedelta(days=2)

    def test_valid_weeks(self) -> None:
        result = _parse_lookback("P1W")
        assert result == timedelta(weeks=1)

    def test_rejects_time_component(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError):
            _parse_lookback("PT6H")

    def test_rejects_invalid_iso_string(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError):
            _parse_lookback("not-a-duration")


class TestParseDateRange:
    def test_date_range_computation_with_lookback(self) -> None:
        """Test that the lookback option generates expected date range"""
        end_date = date(2024, 3, 10)
        lookback = timedelta(days=5)

        start_date, result_end = _parse_date_range(None, lookback, end_date)

        assert result_end == datetime(2024, 3, 10)
        assert start_date == datetime(2024, 3, 5)

    def test_zero_lookback(self) -> None:
        end_date = date(2024, 3, 10)
        lookback = timedelta(days=0)

        start_date, _ = _parse_date_range(None, lookback, end_date)
        assert start_date == datetime(2024, 3, 10)

    def test_date_range_computation_with_start_date(self) -> None:
        """Test that the start date option generates expected date range"""
        end_date = date(2024, 3, 10)
        start_date = date(2024, 3, 1)

        start_date, result_end = _parse_date_range(start_date, None, end_date)

        assert result_end == datetime(2024, 3, 10)
        assert start_date == datetime(2024, 3, 1)

    def test_start_date_equals_end_date(self) -> None:
        """Test that the error raised if start date = end date"""
        end_date = date(2024, 3, 10)
        start_date = date(2024, 3, 10)

        with pytest.raises(argparse.ArgumentTypeError):
            _parse_date_range(start_date, None, end_date)

    def test_start_date_after_end_date(self) -> None:
        """Test that the error raised if start date > end date"""
        end_date = date(2024, 3, 10)
        start_date = date(2025, 3, 10)

        with pytest.raises(argparse.ArgumentTypeError):
            _parse_date_range(start_date, None, end_date)

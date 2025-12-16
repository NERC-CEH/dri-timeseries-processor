import argparse
from collections import Counter
from datetime import date, timedelta

import pytest
from freezegun import freeze_time

from new_processor.cli.cli import _parse_date_range, _parse_lookback, parse_args
from new_processor.cli.selection import (
    CrossProductSelectionSpec,
    ExplicitSelectionSpec,
    RootQuery,
)
from new_processor.utils.urls import SITE_URI


class TestParseArgs:
    @pytest.mark.parametrize(
        "selections, expected_queries",
        [
            ([["SITE1", "TA", "P1D"]], [RootQuery([f"{SITE_URI}/SITE1"], ["TA"], ["P1D"])]),
            (
                [["SITE1", "TA", "P1D"], ["SITE2", "RH", "PT30M"]],
                [
                    RootQuery([f"{SITE_URI}/SITE1"], ["TA"], ["P1D"]),
                    RootQuery([f"{SITE_URI}/SITE2"], ["RH"], ["PT30M"]),
                ],
            ),
        ],
    )
    def test_explicit_selection(self, selections: list, expected_queries: list) -> None:
        args = ["--network", "a_network"]
        for site_id, variable, periodicity in selections:
            args.append("--selection")
            args.append(site_id)
            args.append(variable)
            args.append(periodicity)

        cfg = parse_args(args)

        assert isinstance(cfg.selection, ExplicitSelectionSpec)
        queries = cfg.selection.root_queries
        assert Counter(queries) == Counter(expected_queries)

    @pytest.mark.parametrize(
        "selection",
        [
            "TA P1D",
            "SITE1 P1D",
            "SITE1 TA",
        ],
    )
    def test_explicit_selection_error(self, selection: list) -> None:
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
    def test_explicit_selection_error_additional_args(self, selection: list) -> None:
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

        assert isinstance(cfg.selection, CrossProductSelectionSpec)
        expected_queries = [RootQuery([f"{SITE_URI}/SITE1", f"{SITE_URI}/SITE2"], ["TA", "RH"], ["P1D"])]
        assert cfg.selection.root_queries == expected_queries

    @pytest.mark.parametrize(
        "args, expected_queries",
        [
            (["--variables", "TA"], [RootQuery(None, ["TA"], None)]),
            (["--sites", "SITE1"], [RootQuery([f"{SITE_URI}/SITE1"], None, None)]),
            (["--periodicities", "P1D"], [RootQuery(None, None, ["P1D"])]),
        ],
    )
    def test_cross_product_with_missing_dimensions(self, args: list, expected_queries: list) -> None:
        cfg = parse_args(args + ["--network", "a_network"])
        assert cfg.selection.root_queries == expected_queries

    def test_explicit_and_cross_product(self) -> None:
        """Test that providing both explicit and cross product arguments raises an error"""
        with pytest.raises(SystemExit):
            parse_args(
                [
                    "--network",
                    "a_network",
                    "--selection",
                    "SITE1",
                    "TA",
                    "P1D",
                    "--sites",
                    "SITE1",
                    "--variables",
                    "TA",
                    "RH",
                ]
            )

    def test_no_network_error(self) -> None:
        """Test that not providing a network raises an error"""
        with pytest.raises(SystemExit):
            parse_args(["--selection", "SITE1", "TA", "P1D"])

    @freeze_time("2025-01-01")
    def test_lookback_from_default(self) -> None:
        """Test that lookback works from the default end date"""
        cfg = parse_args(["--network", "a_network", "--lookback", "P2D"])
        assert cfg.end_date == date(2025, 1, 1)
        assert cfg.start_date == date(2024, 12, 30)

    @freeze_time("2025-01-01")
    def test_lookback_from_specified(self) -> None:
        """Test that lookback works from a specified end date"""
        cfg = parse_args(["--network", "a_network", "--end-date", "2025-03-31", "--lookback", "P2D"])
        assert cfg.end_date == date(2025, 3, 31)
        assert cfg.start_date == date(2025, 3, 29)

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
    def test_date_range_computation(self) -> None:
        end_date = date(2024, 3, 10)
        lookback = timedelta(days=5)

        start_date, result_end = _parse_date_range(lookback, end_date)

        assert result_end == end_date
        assert start_date == date(2024, 3, 5)

    def test_zero_lookback(self) -> None:
        end_date = date(2024, 3, 10)
        lookback = timedelta(days=0)

        start_date, _ = _parse_date_range(lookback, end_date)
        assert start_date == end_date

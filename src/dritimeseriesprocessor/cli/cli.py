"""
Command-line interface parsing for time series processing runs.

This module is responsible for parsing CLI arguments to capture user intent regarding:
- which network to process (for dimension-based modes)
- the temporal processing window
- dataset selection mode (explicit, cross-product, or from-datasets), with specific arguments
"""

import argparse
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

import isodate

from dritimeseriesprocessor.cli.selection import (
    DatasetIdSelection,
    DimensionSelection,
    ListSitesSelection,
    RunConfig,
    Selection,
)
from dritimeseriesprocessor.utils.enums import CliSelectionMode
from dritimeseriesprocessor.utils.time_utils import to_datetime
from dritimeseriesprocessor.utils.urls import DATASET_URI, SITE_URI


def parse_args(argv: list[str]) -> RunConfig:
    """Parse CLI arguments and construct a validated RunConfig.

    Args:
        argv: List of command-line arguments.

    Returns:
        A validated RunConfig representing user intent for the processing run.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    start_date, end_date = _parse_date_range(
        start_date=args.start_date,
        end_date=args.end_date,
        lookback=args.lookback,
    )

    selection = _parse_selection_mode(args, parser)

    return RunConfig(
        mode=CliSelectionMode(args.mode),
        selection=selection,
        start_date=start_date,
        end_date=end_date,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Construct and return the ArgumentParser for the CLI.

    Returns:
        A configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="timeseries-processor",
        description="Process time series data through processing pipelines",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    date_range_parent = _build_date_range_parent()
    network_parent = _build_network_parent()
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # Mode A: explicit selections.
    # Individual dataset specifications for fine-grained control. Can be specified multiple times.
    # Each --selection option is a combination of site, variable, and periodicity.
    # Example: --selection SITE1 TA PT30M --selection SITE2 PRECIP P1D
    selection_parser = subparsers.add_parser(
        CliSelectionMode.EXPLICIT.value, parents=[date_range_parent, network_parent]
    )
    selection_parser.add_argument(
        "--selection",
        nargs=3,
        required=True,
        action=SelectionAction,
        metavar=("SITE", "VARIABLE", "PERIODICITY"),
        help="Repeatable explicit selection: --selection SITE1 TA PT30M --selection SITE2 PRECIP P1D",
    )

    # Mode B: cross-product dimension selectors.
    # Intended for bulk processing - process same variables from multiple sites.
    cross_parser = subparsers.add_parser(
        CliSelectionMode.CROSS_PRODUCT.value, parents=[date_range_parent, network_parent]
    )
    cross_parser.add_argument(
        "--sites", nargs="+", help="Space-separated list, e.g. ALIC1 BUNNY. If omitted, find all sites for network."
    )
    cross_parser.add_argument(
        "--variables", nargs="+", help="Space-separated list, e.g. TA PA. If omitted, find all variables for all sites."
    )
    cross_parser.add_argument(
        "--periodicities", nargs="+", help="Space-separated list, e.g. PT30M P1D. If omitted, find all periodicities."
    )

    # Mode C: explicit dataset IDs.
    # Request datasets directly by ID - works for both TimeSeriesDataset and ObservationDataset records.
    # No network required - the dataset ID is self-contained.
    datasets_parser = subparsers.add_parser(CliSelectionMode.FROM_DATASETS.value, parents=[date_range_parent])
    datasets_parser.add_argument(
        "--datasets",
        nargs="+",
        required=True,
        help="Space-separated dataset IDs, e.g. flux-plynl-processed.",
    )

    # Utility command: list all site IDs for a network as a JSON array.
    # Used by the Argo workflow fan-out step.
    subparsers.add_parser(CliSelectionMode.LIST_SITES.value, parents=[date_range_parent, network_parent])

    return parser


def _build_date_range_parent() -> argparse.ArgumentParser:
    """Build a parent parser containing only date-range arguments, shared by all subcommands.

    Returns:
        Parent argument parser with date-range args.
    """
    parser = argparse.ArgumentParser(add_help=False)

    start_date_group = parser.add_mutually_exclusive_group()
    start_date_group.add_argument(
        "--lookback",
        type=_parse_lookback,
        default="P2D",
        help=(
            "ISO8601 duration defining how far back from end-date to process. Should be a combination of "
            "days, weeks, months or years:\nP1D: previous day\nP1Y: previous year\nPT6H: invalid as using hours. "
            "Cannot be used together with --start-date."
        ),
    )
    start_date_group.add_argument(
        "--start-date",
        type=date.fromisoformat,
        help="Start date (YYYY-MM-DD). Cannot be used together with --lookback.",
    )

    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=date.today(),
        help="End date (YYYY-MM-DD, default: today)",
    )
    return parser


def _build_network_parent() -> argparse.ArgumentParser:
    """Build a parent parser containing only the --network argument.

    Returns:
        Parent argument parser with --network arg.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--network", required=True)
    return parser


def _parse_lookback(value: str) -> timedelta:
    """Parse an ISO 8601 duration string into a timedelta.

    The lookback duration defines how far back from the end date processing should occur.
    Time components (hours, minutes, seconds) are not permitted.

    Args:
        value: ISO 8601 duration string (e.g. 'P2D', 'P1Y').

    Returns:
        A timedelta representing the lookback period.
    """
    if "T" in value:
        raise argparse.ArgumentTypeError("--lookback must not contain a time component")

    try:
        lookback = isodate.parse_duration(value)
    except ValueError:
        raise argparse.ArgumentTypeError("--lookback must be a valid ISO8601 duration string")
    return lookback


def _parse_date_range(start_date: date | None, lookback: timedelta | None, end_date: date) -> tuple[datetime, datetime]:
    """Derive the start and end dates for processing, normalising both to datetime objects

    Args:
        start_date: Start date for the processing window (mutually exclusive of lookback).
        end_date: End date for the processing window.
        lookback: How far back from the end date to process (mutually exclusive of start_date).

    Returns:
        Tuple of (start_date, end_date).
    """
    if start_date is not None:
        if start_date >= end_date:
            raise argparse.ArgumentTypeError("--start-date must be earlier than --end-date")
        return to_datetime(start_date), to_datetime(end_date)

    if lookback is None:
        raise argparse.ArgumentTypeError("Either --start-date or --lookback must be provided")

    start_date = end_date - lookback
    return to_datetime(start_date), to_datetime(end_date)


def _parse_selection_mode(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[Selection]:
    """Determine the dataset selection mode and construct the appropriate selection objects.

    Args:
        args: Parsed CLI arguments.
        parser: ArgumentParser instance used to report validation errors.

    Returns:
        A list of Selection objects representing user selection intent.
    """
    mode = CliSelectionMode(args.mode)
    if mode == CliSelectionMode.EXPLICIT:
        return _parse_explicit_selection(args)

    if mode == CliSelectionMode.CROSS_PRODUCT:
        return _parse_cross_product_selection(args)

    if mode == CliSelectionMode.FROM_DATASETS:
        return _parse_dataset_id_selection(args)

    if mode == CliSelectionMode.LIST_SITES:
        return [ListSitesSelection(network=args.network)]

    parser.error(f"Invalid selection mode: {mode}. Expected one of: {[m.value for m in CliSelectionMode]}")


def _parse_explicit_selection(args: argparse.Namespace) -> list[DimensionSelection]:
    """Parse explicit dataset selection arguments.

    Args:
        args: Parsed CLI arguments containing explicit selection values.

    Returns:
        A list of DimensionSelection objects representing user selection intent.
    """
    return [
        DimensionSelection(
            network=args.network,
            sites=[f"{SITE_URI}/{site}"],
            variables=[variable],
            periodicities=[periodicity],
        )
        for site, variable, periodicity in args.selection
    ]


def _parse_dataset_id_selection(args: argparse.Namespace) -> list[DatasetIdSelection]:
    """Parse explicit dataset ID selection arguments.

    Args:
        args: Parsed CLI arguments containing dataset ID values.

    Returns:
        A list containing a single DatasetIdSelection with fully-qualified dataset URIs.
    """
    dataset_ids = [f"{DATASET_URI}/{ds_id}" for ds_id in args.datasets]
    return [DatasetIdSelection(dataset_ids=dataset_ids)]


def _parse_cross_product_selection(args: argparse.Namespace) -> list[DimensionSelection]:
    """Parse cross-product dataset selection arguments.

    Args:
       args: Parsed CLI arguments containing cross-product selection values.

    Returns:
       A list of DimensionSelection objects representing user selection intent.
    """
    sites = [f"{SITE_URI}/{site}" for site in args.sites] if args.sites else None
    return [
        DimensionSelection(
            network=args.network, sites=sites, variables=args.variables, periodicities=args.periodicities
        )
    ]


class SelectionAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        """Custom argparse Action for validating explicit dataset selection arguments.

        This action is used for the ``--selection`` CLI option, which represents a selection in the form:
        --selection SITE VARIABLE PERIODICITY

        Although ``nargs=3`` enforces that exactly three tokens are provided, argparse will happily consume the
        next option flag (e.g. ``--end-date``) as a positional value if the user omits one of the required
        arguments.
        """
        if not isinstance(values, list):
            parser.error("--selection requires exactly 3 non-empty values: SITE VARIABLE PERIODICITY")

        if any(not v or v.startswith("-") for v in values):
            parser.error("--selection requires exactly 3 non-empty values: SITE VARIABLE PERIODICITY")

        selections = getattr(namespace, self.dest, None)
        if selections is None:
            selections = []
            setattr(namespace, self.dest, selections)

        selections.append(values)

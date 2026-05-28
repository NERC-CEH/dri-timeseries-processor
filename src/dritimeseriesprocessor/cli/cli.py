"""
Command-line interface parsing for time series processing runs.

This module is responsible for parsing CLI arguments to capture user intent regarding:
- which network to process
- the temporal processing window
- dataset selection mode (explicit, cross-product, or eddypro), with specific arguments
"""

import argparse
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

import isodate

from dritimeseriesprocessor.cli.selection import RunConfig, SelectionOption
from dritimeseriesprocessor.utils.enums import CliSelectionMode
from dritimeseriesprocessor.utils.time_utils import to_datetime
from dritimeseriesprocessor.utils.urls import SITE_URI


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
        network=args.network,
        selection=selection,
        start_date=start_date,
        end_date=end_date,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Construct and return the ArgumentParser for the CLI.

    Defines all supported command-line options, including network selection, temporal parameters,
    dataset selection modes (explicit, cross-product, eddypro), and utility commands (list-sites).

    Returns:
        A configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="timeseries-processor",
        description="Process time series data through processing pipelines",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parent = _build_parent_parser()
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # Mode A: explicit selections.
    # Individual dataset specifications for fine-grained control. Can be specified multiple times.
    # Each --selection option is a combination of site, variable, and periodicity. "
    # Example: --selection SITE1 TA PT30M --selection SITE2 PRECIP P1D"
    selection_parser = subparsers.add_parser(CliSelectionMode.EXPLICIT.value, parents=[parent])
    selection_parser.add_argument(
        "--selection",
        nargs=3,
        required=True,
        action=SelectionAction,
        metavar=("SITE", "VARIABLE", "PERIODICITY"),
        help="Repeatable explicit selection: --selection SITE1 TA PT30M --selection SITE2 PRECIP P1D",
    )

    # Mode B: cross-product dimension selectors
    # Intended for a bulk processing mode - process same variables from multiple sites.
    cross_parser = subparsers.add_parser(CliSelectionMode.CROSS_PRODUCT.value, parents=[parent])
    cross_parser.add_argument(
        "--sites", nargs="+", help="Space-separated list, e.g. ALIC1 BUNNY. If omitted, find all sites for network."
    )
    cross_parser.add_argument(
        "--variables", nargs="+", help="Space-separated list, e.g. TA PA. If omitted, find all variables for all sites."
    )
    cross_parser.add_argument(
        "--periodicities", nargs="+", help="Space-separated list, e.g. PT30M P1D. If omitted, find all periodicities."
    )

    # Mode C: EddyPro flux processing
    # File-based processing via EddyPro binary — operates on entire sites, not individual variables.
    eddypro_parser = subparsers.add_parser(CliSelectionMode.EDDYPRO.value, parents=[parent])
    eddypro_parser.add_argument(
        "--sites",
        nargs="+",
        help="Space-separated site identifiers, e.g. PLYNL. If omitted, process all sites for network.",
    )

    # Utility command: list all site IDs for a network as a JSON array.
    # Used by the Argo workflow fan-out step. Routed in __main__.py before parse_args is called.
    subparsers.add_parser(CliSelectionMode.LIST_SITES.value, parents=[parent])

    return parser


def _build_parent_parser() -> argparse.ArgumentParser:
    """Build a parent parser for the sub-parsers to use, so they can share common arguments

    Returns:
        Parent argument parser
    """
    parser = argparse.ArgumentParser(add_help=False)

    parser.add_argument("--network", required=True)

    # User should specify lookback OR start date
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


def _parse_selection_mode(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[SelectionOption]:
    """Determine the dataset selection mode and construct the appropriate selection options.

    The CLI supports three mutually exclusive selection modes:
        - Explicit selection via repeated --selection arguments
        - Cross-product selection via --sites / --variables / --periodicities

    Args:
        args: Parsed CLI arguments.
        parser: ArgumentParser instance used to report validation errors.

    Returns:
        A list of SelectionOptions representing user selection intent.
    """
    mode = CliSelectionMode(args.mode)
    if mode == CliSelectionMode.EXPLICIT:
        return _parse_explicit_selection(args)

    if mode == CliSelectionMode.CROSS_PRODUCT:
        return _parse_cross_product_selection(args)

    if mode == CliSelectionMode.EDDYPRO:
        return _parse_eddypro_selection(args)

    if mode == CliSelectionMode.LIST_SITES:
        return []

    parser.error(f"Invalid selection mode: {mode}. Expected one of: {[m.value for m in CliSelectionMode]}")


def _parse_explicit_selection(args: argparse.Namespace) -> list[SelectionOption]:
    """Parse explicit dataset selection arguments.

    Each explicit selection is converted into a selection option representing a fully specified
    (site, variable, periodicity) dataset request.

    Args:
        args: Parsed CLI arguments containing explicit selection values.

    Returns:
        A list of SelectionOptions representing user selection intent.
    """
    return [
        (SelectionOption([f"{SITE_URI}/{site}"], [variable], [periodicity]))
        for site, variable, periodicity in args.selection
    ]


def _parse_cross_product_selection(args: argparse.Namespace) -> list[SelectionOption]:
    """Parse cross-product dataset selection arguments.

    Constructs a selection specification with optional constraints over sites, variables, and periodicities.
    Any dimension left unspecified is treated as unconstrained and will be expanded downstream using metadata.

    Args:
       args: Parsed CLI arguments containing cross-product selection values.

    Returns:
       A list of SelectionOptions representing user selection intent.
    """
    sites = [f"{SITE_URI}/{site}" for site in args.sites] if args.sites else None
    return [SelectionOption(sites, args.variables, args.periodicities)]


def _parse_eddypro_selection(args: argparse.Namespace) -> list[SelectionOption]:
    """Parse EddyPro site selection arguments.

    EddyPro operates at site level — no variables or periodicities.

    If ``--sites`` is provided, the selection is restricted to those site identifiers.
    If omitted, sites are left unconstrained (ALL) and will be expanded downstream by
    the execution mode (e.g. local fixtures in EddyPro dev mode).

    Args:
        args: Parsed CLI arguments containing EddyPro selection values.

    Returns:
        A list of SelectionOptions representing user selection intent.
    """
    return [SelectionOption(sites=args.sites)]


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

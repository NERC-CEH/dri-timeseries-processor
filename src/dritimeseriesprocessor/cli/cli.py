"""
Command-line interface parsing for time series processing runs.

This module is responsible for parsing CLI arguments to capture user intent regarding:
- which network to process (for dimension-based modes)
- the temporal processing window (not used in historic mode, which works out each site's own dates)
- dataset selection mode (explicit, cross-product, from-datasets or historic), with specific arguments
"""

import argparse
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

import isodate

from dritimeseriesprocessor.cli.selection import (
    DatasetIdSelection,
    DimensionSelection,
    HistoricRunConfig,
    HistoricSelection,
    ListSitesRunConfig,
    ListSitesSelection,
    RunConfig,
    Selection,
    StandardRunConfig,
)
from dritimeseriesprocessor.utils.enums import CliSelectionMode
from dritimeseriesprocessor.utils.time_utils import to_datetime
from dritimeseriesprocessor.utils.urls import DATASET_URI, SITE_URI


def parse_args(argv: list[str]) -> RunConfig:
    """Parse CLI arguments and construct a validated run configuration for the chosen mode.

    Args:
        argv: List of command-line arguments.

    Returns:
        A validated run configuration representing user intent for the processing run.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    match CliSelectionMode(args.mode):
        case CliSelectionMode.HISTORIC:
            return create_historic_run_config(args)

        case CliSelectionMode.LIST_SITES:
            return create_list_sites_run_config(parser, args)

        case CliSelectionMode.EXPLICIT:
            return create_explicit_run_config(args)

        case CliSelectionMode.CROSS_PRODUCT:
            return create_cross_product_run_config(args)

        case CliSelectionMode.FROM_DATASETS:
            return create_from_datasets_run_config(args)


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
        "--sites",
        nargs="+",
        help="Space-separated list, e.g. cosmos-alic1 cosmos-bunny. If omitted, find all sites for network.",
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

    # Mode D: Historic mode
    # Process every dataset for the sites, over each site's full operating dates.
    historic_parser = subparsers.add_parser(CliSelectionMode.HISTORIC.value, parents=[network_parent])
    historic_parser.add_argument(
        "--sites",
        nargs="+",
        help="Space-separated list, e.g. cosmos-alic1 cosmos-bunny. If omitted, process all sites for the network.",
    )

    # Utility command: list site IDs for a network as a JSON array.
    # Used by the Argo workflow fan-out step.
    list_sites_parser = subparsers.add_parser(
        CliSelectionMode.LIST_SITES.value, parents=[date_range_parent, network_parent]
    )
    list_sites_parser.add_argument(
        "--sites",
        nargs="+",
        help="Space-separated list, e.g. cosmos-alic1 cosmos-bunny. If omitted, list all sites for network.",
    )
    list_sites_parser.add_argument(
        "--historic",
        action="store_true",
        help=(
            "List every site the network has ever had, including closed ones, with no date check. "
            "Cannot be used together with --lookback, --start-date or --end-date."
        ),
    )

    return parser


def _build_date_range_parent() -> argparse.ArgumentParser:
    """Build a parent parser containing only date-range arguments, shared by all subcommands.

    The arguments default to None so that `list-sites --historic` can tell whether any were given. The defaults
    (a `P2D` lookback, ending today) are applied in `_parse_date_range`.

    Returns:
        Parent argument parser with date-range args.
    """
    parser = argparse.ArgumentParser(add_help=False)

    start_date_group = parser.add_mutually_exclusive_group()
    start_date_group.add_argument(
        "--lookback",
        type=_parse_lookback,
        help=(
            "ISO8601 duration defining how far back from end-date to process (default: P2D). Should be a combination "
            "of days, weeks, months or years:\nP1D: previous day\nP1Y: previous year\nPT6H: invalid as using hours. "
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


def _parse_date_range(
    start_date: date | None, lookback: timedelta | None, end_date: date | None
) -> tuple[datetime, datetime]:
    """Derive the start and end dates for processing, normalising both to datetime objects

    Args:
        start_date: Start date for the processing window (mutually exclusive of lookback).
        lookback: How far back from the end date to process (mutually exclusive of start_date). Defaults to P2D when
            neither this or start_date is given.
        end_date: End date for the processing window. Defaults to today.

    Returns:
        Tuple of (start_date, end_date).
    """
    if end_date is None:
        end_date = date.today()

    if start_date is not None:
        if start_date > end_date:
            raise argparse.ArgumentTypeError("--start-date must be earlier than --end-date")
        return to_datetime(start_date), to_datetime(end_date)

    if lookback is None:
        lookback = timedelta(days=2)

    start_date = end_date - lookback
    return to_datetime(start_date), to_datetime(end_date)


def _parse_date_args(args: argparse.Namespace) -> tuple[datetime, datetime]:
    """Derive the start and end dates for processing from the parsed date range arguments.

    Args:
        args: Parsed CLI arguments containing the date range values.

    Returns:
        Tuple of (start_date, end_date).
    """
    return _parse_date_range(start_date=args.start_date, lookback=args.lookback, end_date=args.end_date)


def _site_uris(sites: list[str] | None) -> list[str] | None:
    """Turn site IDs from the CLI into full metadata API site URIs.

    Args:
        sites: Site IDs, e.g. cosmos-alic1, or None if no sites were given.

    Returns:
        The site URIs, or None if no sites were given.
    """
    return [f"{SITE_URI}/{site}" for site in sites] if sites else None


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


def create_historic_run_config(args: argparse.Namespace) -> HistoricRunConfig:
    """Create the historic run config.

    Args:
        args: Parsed CLI arguments containing the historic run options.

    Returns:
        A historic run configuration.
    """
    site_list = _site_uris(args.sites)
    selection = HistoricSelection(network=args.network, sites=site_list)
    return HistoricRunConfig(selection)


def create_list_sites_run_config(parser: argparse.ArgumentParser, args: argparse.Namespace) -> ListSitesRunConfig:
    """Create the list sites run config

    Args:
        parser: The parser, to report `--historic` given together with a date argument.
        args: Parsed CLI arguments containing the list-sites values.

    Returns:
        A list-sites run configuration, with no dates if `--historic` was given.
    """
    selection = ListSitesSelection(network=args.network, sites=_site_uris(args.sites))
    if not args.historic:
        return ListSitesRunConfig(selection, *_parse_date_args(args))

    if any(date_arg is not None for date_arg in (args.lookback, args.start_date, args.end_date)):
        parser.error("--historic cannot be used together with --lookback, --start-date or --end-date")
    return ListSitesRunConfig(selection, start_date=None, end_date=None)


def create_explicit_run_config(args: argparse.Namespace) -> StandardRunConfig:
    """Create the run config for explicit selections.

    Args:
        args: Parsed CLI arguments containing explicit selection values and the date range.

    Returns:
        A standard run configuration, with one selection per --selection given.
    """
    selection: list[Selection] = [
        DimensionSelection(
            network=args.network,
            sites=[f"{SITE_URI}/{site}"],
            variables=[variable],
            periodicities=[periodicity],
        )
        for site, variable, periodicity in args.selection
    ]
    start_date, end_date = _parse_date_args(args)
    return StandardRunConfig(selection, start_date, end_date)


def create_cross_product_run_config(args: argparse.Namespace) -> StandardRunConfig:
    """Create the run config for cross-product selections.

    Args:
        args: Parsed CLI arguments containing cross-product selection values and the date range.

    Returns:
        A standard run configuration, with one selection covering every combination of the given sites, variables
        and periodicities.
    """
    selection: list[Selection] = [
        DimensionSelection(
            network=args.network,
            sites=_site_uris(args.sites),
            variables=args.variables,
            periodicities=args.periodicities,
        )
    ]
    start_date, end_date = _parse_date_args(args)
    return StandardRunConfig(selection, start_date, end_date)


def create_from_datasets_run_config(args: argparse.Namespace) -> StandardRunConfig:
    """Create the run config for datasets requested by ID.

    Args:
        args: Parsed CLI arguments containing dataset ID values and the date range.

    Returns:
        A standard run configuration, with one selection holding the full dataset URIs.
    """
    dataset_ids = [f"{DATASET_URI}/{dataset_id}" for dataset_id in args.datasets]
    selection: list[Selection] = [DatasetIdSelection(dataset_ids=dataset_ids)]
    start_date, end_date = _parse_date_args(args)
    return StandardRunConfig(selection, start_date, end_date)

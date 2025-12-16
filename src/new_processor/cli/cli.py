"""
Command-line interface parsing for time series processing runs.

This module is responsible for parsing CLI arguments to capture user intent regarding:
- which network to process
- the temporal processing window
- dataset selection mode (explicit or cross-product), with specific arguments
"""

import argparse
from datetime import date, timedelta

import isodate

from new_processor.cli.selection import (
    CrossProductSelectionSpec,
    ExplicitSelectionSpec,
    RootQuery,
    RunConfig,
    SelectionSpec,
)
from new_processor.utils.urls import SITE_URI


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
        lookback=args.lookback,
        end_date=args.end_date,
    )

    selection = _parse_selection_mode(args, parser)

    return RunConfig(
        network=args.network,
        selection=selection,
        start_date=start_date,
        end_date=end_date,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Construct and return the ArgumentParser for the CLI.

    Defines all supported command-line options, including network selection, temporal parameters, and
    dataset selection modes (explicit and cross-product).

    Returns:
        A configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="timeseries-processor",
        description="Process time series data through processing pipelines",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument("--network", required=True)
    parser.add_argument(
        "--lookback",
        type=_parse_lookback,
        default="P2D",
        help=(
            "ISO8601 duration defining how far back from end-date to process. Should be a combination of "
            "days, weeks, months or years:\nP1D: previous day\nP1Y: previous year\nPT6H: invalid as using hours"
        ),
    )
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=date.today(),
        help="End date (YYYY-MM-DD, default: today)",
    )

    # Mode A: explicit selections.
    # Individual dataset specifications for fine-grained control. Can be specified multiple times.
    # Each --selection option is a combination of site, variable, and periodicity. "
    # Example: --selection SITE1 TA PT30M --selection SITE2 PRECIP P1D"
    parser.add_argument(
        "--selection",
        nargs=3,
        action=SelectionAction,
        metavar=("SITE", "VARIABLE", "PERIODICITY"),
        help="Repeatable explicit selection: --selection SITE1 TA PT30M --selection SITE2 PRECIP P1D",
    )

    # Mode B: cross-product selectors
    # Intended for a bulk processing mode - process same variables from multiple sites.
    parser.add_argument("--sites", nargs="+", help="Space-separated list, e.g. ALIC1 BUNNY")
    parser.add_argument("--variables", nargs="+", help="Space-separated list, e.g. TA PA")
    parser.add_argument("--periodicities", nargs="+", help="Space-separated list, e.g. PT30M P1D")

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


def _parse_date_range(lookback: timedelta, end_date: date) -> tuple[date, date]:
    """Derive the start and end dates for processing.

    Args:
        lookback: How far back from the end date to process.
        end_date: End date for the processing window.

    Returns:
        Tuple of (start_date, end_date).
    """
    start_date = end_date - lookback
    return start_date, end_date


def _parse_selection_mode(args: argparse.Namespace, parser: argparse.ArgumentParser) -> SelectionSpec:
    """Determine the dataset selection mode and construct the appropriate SelectionSpec.

    The CLI supports two mutually exclusive selection modes:
        - Explicit selection via repeated --selection arguments
        - Cross-product selection via --sites / --variables / --periodicities

    Args:
        args: Parsed CLI arguments.
        parser: ArgumentParser instance used to report validation errors.

    Returns:
        A SelectionSpec instance representing user selection intent.
    """
    has_explicit_selection = args.selection is not None
    has_cross_product = any([args.sites, args.variables, args.periodicities])

    if has_explicit_selection and has_cross_product:
        parser.error("Use either --selection (repeatable) OR --sites/--variables/--periodicities, not both.")

    if has_explicit_selection:
        return _parse_explicit_selection(args)
    else:
        return _parse_cross_product_selection(args)


def _parse_explicit_selection(args: argparse.Namespace) -> SelectionSpec:
    """Parse explicit dataset selection arguments.

    Each explicit selection is converted into a RootQuery representing a fully specified (site, variable, periodicity)
    dataset request.

    Args:
        args: Parsed CLI arguments containing explicit selection values.

    Returns:
        An ExplicitSelectionSpec representing the requested datasets.
    """
    return ExplicitSelectionSpec(
        explicit=[
            RootQuery(sites=[f"{SITE_URI}/{site}"], variables=[variable], periodicities=[periodicity])
            for site, variable, periodicity in args.selection
        ]
    )


def _parse_cross_product_selection(args: argparse.Namespace) -> SelectionSpec:
    """Parse cross-product dataset selection arguments.

    Constructs a selection specification with optional constraints over sites, variables, and periodicities.
    Any dimension left unspecified is treated as unconstrained and will be expanded downstream using metadata.

    Args:
       args: Parsed CLI arguments containing cross-product selection values.

    Returns:
       A CrossProductSelectionSpec representing the selection constraints.
    """
    return CrossProductSelectionSpec(
        sites=[f"{SITE_URI}/{site}" for site in args.sites],
        variables=args.variables,
        periodicities=args.periodicities,
    )


class SelectionAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: list[str],
        option_string: str | None = None,
    ) -> None:
        """Custom argparse Action for validating explicit dataset selection arguments.

        This action is used for the ``--selection`` CLI option, which represents a selection in the form:
        --selection SITE VARIABLE PERIODICITY

        Although ``nargs=3`` enforces that exactly three tokens are provided, argparse will happily consume the
        next option flag (e.g. ``--end-date``) as a positional value if the user omits one of the required
        arguments.
        """
        if any(not v or v.startswith("-") for v in values):
            parser.error("--selection requires exactly 3 non-empty values: SITE VARIABLE PERIODICITY")

        selections = getattr(namespace, self.dest, None)
        if selections is None:
            selections = []
            setattr(namespace, self.dest, selections)

        selections.append(values)

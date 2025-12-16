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
    """Parse CLI arguments and return a validated RunConfig."""
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
        action="append",
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
    if "T" in value:
        raise argparse.ArgumentTypeError("--lookback must not contain a time component")

    try:
        lookback = isodate.parse_duration(value)
    except ValueError:
        raise argparse.ArgumentTypeError("--lookback must be a valid ISO8601 duration string")
    return lookback


def _parse_date_range(lookback: timedelta, end_date: date) -> tuple[date, date]:
    """Parse lookback and end-date arguments into a start and end date range."""
    start_date = end_date - lookback
    return start_date, end_date


def _parse_selection_mode(args: argparse.Namespace, parser: argparse.ArgumentParser) -> SelectionSpec:
    """Determine selection mode and build a SelectionSpec."""
    has_explicit_selection = args.selection is not None
    has_cross_product = any([args.sites, args.variables, args.periodicities])

    if has_explicit_selection and has_cross_product:
        parser.error("Use either --selection (repeatable) OR --sites/--variables/--periodicities, not both.")

    if has_explicit_selection:
        return _parse_explicit_selection(args)
    else:
        return _parse_cross_product_selection(args)


def _parse_explicit_selection(args: argparse.Namespace) -> SelectionSpec:
    return ExplicitSelectionSpec(
        explicit=[
            RootQuery(sites=[f"{SITE_URI}/{site}"], variables=[variable], periodicities=[periodicity])
            for site, variable, periodicity in args.selection
        ]
    )


def _parse_cross_product_selection(args: argparse.Namespace) -> SelectionSpec:
    return CrossProductSelectionSpec(
        sites=args.sites,
        variables=args.variables,
        periodicities=args.periodicities,
    )

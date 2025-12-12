import argparse
from datetime import date, timedelta

import isodate

from new_processor.cli.models import ExplicitSelection, RunConfig, SelectionSpec


def parse_args(argv: list[str]) -> RunConfig:
    """Parse CLI arguments and return a validated RunConfig."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    start_date, end_date = _parse_date_range(
        lookback=args.lookback,
        end_date=args.end_date,
    )

    selection = _parse_selection(args, parser)

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
        default=date.today().isoformat(),
        help="End date (YYYY-MM-DD, default: today)",
    )

    # Mode A: explicit selections.
    # Individual dataset specifications for fine-grained control. Can be specified multiple times.
    # Each --timeseries option is a combination of site, variable, and periodicity. "
    # Example: --timeseries SITE1 TA PT30M --timeseries SITE2 PRECIP P1D"
    parser.add_argument(
        "--timeseries",
        nargs=3,
        action="append",
        metavar=("SITE", "COLUMN", "PERIODICITY"),
        help="Repeatable explicit selection: --timeseries SITE1 TA PT30M --timeseries SITE2 PRECIP P1D",
    )

    # Mode B: cross-product selectors
    # Intended for a bulk processing mode - process same variables from multiple sites.
    parser.add_argument("--sites", help="Comma-separated list, e.g. ALIC1,BUNNY")
    parser.add_argument("--columns", help="Comma-separated list, e.g. TA,PA")
    parser.add_argument("--periodicities", help="Comma-separated list, e.g. PT30M,P1D")

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


def _parse_selection(args: argparse.Namespace, parser: argparse.ArgumentParser) -> SelectionSpec:
    """Determine selection mode and build a SelectionSpec."""
    has_timeseries = args.timeseries is not None
    has_cross_product = any([args.sites, args.columns, args.periodicities])

    if has_timeseries and has_cross_product:
        parser.error("Use either --timeseries (repeatable) OR --sites/--columns/--periodicities, not both.")

    if not has_timeseries and not has_cross_product:
        parser.error("You must provide either --timeseries or at least one of --sites/--columns/--periodicities.")

    if has_timeseries:
        return _parse_timeseries_selection(args)
    else:
        return _parse_cross_product_selection(args)


def _parse_timeseries_selection(args: argparse.Namespace) -> SelectionSpec:
    return SelectionSpec(
        explicit=[
            ExplicitSelection(
                site=site.upper(),
                column=column.upper(),
                periodicity=periodicity.upper(),
            )
            for site, column, periodicity in args.timeseries
        ]
    )


def _parse_cross_product_selection(args: argparse.Namespace) -> SelectionSpec:
    return SelectionSpec(
        sites=_split_upper(args.sites),
        columns=_split_upper(args.columns),
        periodicities=_split_upper(args.periodicities),
    )


def _split_upper(value: str | None) -> list[str] | None:
    """Split a comma-separated string and normalise to uppercase."""
    if value is None:
        return None

    items = [v.strip() for v in value.split(",") if v.strip()]
    return [v.upper() for v in items] if items else None

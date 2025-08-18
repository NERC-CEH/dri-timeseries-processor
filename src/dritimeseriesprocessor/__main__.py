import sys
from typing import List

from dritimeseriesprocessor import parser
from dritimeseriesprocessor.time_series_processor import TimeSeriesProcessor


def main(args: List[str]) -> None:
    """
    The initial function run when this file is called via the command line.

    Parses the CLI args, before initialising and running the TimeSeriesProcessor class.
    """
    args = parser.parse_args(args)

    time_series_processor = TimeSeriesProcessor(
        sites=args.sites,
        columns=args.columns,
        periodicity=args.periodicity,
        end_date=args.end_date,
        period=args.period,
        network=args.network,
    )
    time_series_processor.run()


if __name__ == "__main__":
    main(sys.argv[1:])

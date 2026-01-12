import logging
import sys

from dritimeseriesprocessor.app.run import run_from_config
from dritimeseriesprocessor.cli.cli import parse_args

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def main(argv: list[str]) -> None:
    run_config = parse_args(argv)
    run_from_config(run_config)


if __name__ == "__main__":
    main(sys.argv[1:])

import sys

from dritimeseriesprocessor.app.run import run_from_config
from dritimeseriesprocessor.cli.cli import parse_args
from dritimeseriesprocessor.configuration.app_config import AppConfig
from dritimeseriesprocessor.setup_logging import setup_logger


def main(argv: list[str]) -> None:
    run_config = parse_args(argv)
    setup_logger(service_name=AppConfig.service_name)
    run_from_config(run_config)


if __name__ == "__main__":
    main(sys.argv[1:])
